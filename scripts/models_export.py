#!/usr/bin/env python3
"""Exporta la precipitació horària dels models (WRF-SMC i, quan hi sigui, AROME) per al visor.

Per a cada model escriu a <sortida>/<model>/:
  precip_h.png   sprite amb la pluja horària de tots els passos (mm/h). Cada píxel codifica el valor en 16 bits:
                 R = alt, G = baix, valor = (R*256+G) * escala mm; 65535 = sense dada. Els passos van en graella (cols columnes).
  meta.json      run, passos, límits (bounds), mida del tile, escala...
i a <sortida>/index.json la llista de models disponibles.
La pluja acumulada (des de l'inici, o en finestres de 3/6/12/24 h) la calcula el navegador sumant passos horaris.

Només processa el run més recent que sigui complet i que no estigui ja exportat (--forca per obligar-ho).
No genera cap figura.

Ús:
  python3 models_export.py --wrf-dir /home/labfire/data/SMC-WRF --arome-dir /home/labfire/data/AROME-CAT --sortida data/models
Requisits: numpy, scipy, Pillow, netCDF4 (WRF) i eccodes (AROME)."""
import argparse
import glob
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ESCALA = 0.01          # mm per unitat codificada
NODATA = 65535
COLS = 7               # columnes de la graella de passos


# ----------------------------------------------------------------------------- utilitats comunes
def merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def lat_de_merc(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def graella_destinacio(s, w, n, e, res_deg):
    """Graella regular en longitud i en y de Mercator (píxels quadrats): així un imageOverlay de Leaflet hi encaixa exactament."""
    res = math.radians(res_deg)
    ny0, ny1 = merc_y(n), merc_y(s)
    W = int(round(math.radians(e - w) / res))
    H = int(round((ny0 - ny1) / res))
    xs = w + (np.arange(W) + 0.5) * (e - w) / W
    ys = ny0 - (np.arange(H) + 0.5) * (ny0 - ny1) / H
    lats = lat_de_merc(ys)
    return xs, lats, W, H


def codifica(v):
    """v: (H, W) mm/h amb NaN = sense dada -> uint16"""
    q = np.where(np.isfinite(v), np.clip(np.round(np.nan_to_num(v) / ESCALA), 0, NODATA - 1), NODATA).astype(np.uint16)
    return q


def escriu_sprite(camps, dest_png):
    """camps: llista (passos) de matrius (H, W) en mm/h. Escriu la graella de tiles en RGB (alt, baix, 0)."""
    n = len(camps)
    H, W = camps[0].shape
    files = math.ceil(n / COLS)
    img = np.zeros((files * H, COLS * W, 3), np.uint8)
    img[..., 0] = 255
    img[..., 1] = 255          # per defecte: sense dada
    for k, c in enumerate(camps):
        q = codifica(c)
        r, cc = divmod(k, COLS)
        img[r * H:(r + 1) * H, cc * W:(cc + 1) * W, 0] = (q >> 8).astype(np.uint8)
        img[r * H:(r + 1) * H, cc * W:(cc + 1) * W, 1] = (q & 255).astype(np.uint8)
        img[r * H:(r + 1) * H, cc * W:(cc + 1) * W, 2] = 0
    Image.fromarray(img, "RGB").save(dest_png, optimize=True)


def escriu_atomic(path, text):
    tmp = str(path) + ".tmp"
    Path(tmp).write_text(text)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- WRF-SMC
RE_DONE = re.compile(r"SMCWRF_d01_(\d{8})_(\d{2})\.done$")


def troba_run_wrf(carpeta, min_passos=2):
    """Retorna (run_datetime, [fitxers per pas]) del run més recent amb .done i fitxers f000.. contigus."""
    cand = []
    for f in glob.glob(os.path.join(carpeta, "SMCWRF_d01_*_*.done")):
        m = RE_DONE.search(os.path.basename(f))
        if m:
            cand.append((m.group(1) + m.group(2), m.group(1), m.group(2)))
    for _, d, h in sorted(cand, reverse=True):
        fitxers = []
        for k in range(0, 200):
            p = os.path.join(carpeta, f"SMCWRF_d01_{d}_{h}_f{k:03d}.nc")
            if not os.path.exists(p):
                break
            fitxers.append(p)
        if len(fitxers) >= min_passos:
            return datetime.strptime(d + h, "%Y%m%d%H").replace(tzinfo=timezone.utc), fitxers
    return None, []


def llegeix_wrf(fitxers):
    import netCDF4 as nc
    acum = []
    lat = lon = None
    for p in fitxers:
        d = nc.Dataset(p)
        if lat is None:
            lat = np.array(d.variables["XLAT"][0], dtype=np.float64)
            lon = np.array(d.variables["XLONG"][0], dtype=np.float64)
        a = np.array(d.variables["RAINNC"][0], dtype=np.float64)
        if "RAINC" in d.variables:
            a = a + np.array(d.variables["RAINC"][0], dtype=np.float64)
        acum.append(a)
        d.close()
    return lat, lon, acum


def exporta_wrf(carpeta, sortida, forca, res_deg):
    run, fitxers = troba_run_wrf(carpeta)
    if run is None:
        print("WRF: cap run complet trobat a", carpeta)
        return None
    dest = Path(sortida) / "wrf"
    meta_p = dest / "meta.json"
    run_txt = run.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not forca and meta_p.exists():
        try:
            m = json.loads(meta_p.read_text())
            if m.get("run_utc") == run_txt and m.get("passos") == len(fitxers):
                print(f"WRF: run {run_txt} ja exportat ({len(fitxers)} passos)")
                return m
        except Exception:
            pass
    print(f"WRF: processant run {run_txt}, {len(fitxers)} fitxers…")
    lat, lon, acum = llegeix_wrf(fitxers)
    horari = [np.zeros_like(acum[0])] + [np.clip(acum[i] - acum[i - 1], 0, None) for i in range(1, len(acum))]
    from scipy.interpolate import LinearNDInterpolator
    s, n = float(lat.min()), float(lat.max())
    w, e = float(lon.min()), float(lon.max())
    xs, lats, W, H = graella_destinacio(s, w, n, e, res_deg)
    pts = np.column_stack([lon.ravel(), lat.ravel()])
    val = np.column_stack([h.ravel() for h in horari])
    interp = LinearNDInterpolator(pts, val)
    X, Y = np.meshgrid(xs, lats)
    R = interp(np.column_stack([X.ravel(), Y.ravel()]))          # (H*W, passos), NaN fora del domini
    camps = [R[:, k].reshape(H, W) for k in range(R.shape[1])]
    dest.mkdir(parents=True, exist_ok=True)
    escriu_sprite(camps, dest / "precip_h.png")
    meta = {"model": "wrf", "nom": "WRF-SMC", "run_utc": run_txt, "pas_h": 1, "passos": len(camps),
            "bounds": [[round(s, 4), round(w, 4)], [round(n, 4), round(e, 4)]], "w": W, "h": H, "cols": COLS,
            "escala": ESCALA, "nodata": NODATA, "fitxer": "precip_h.png", "resolucio_km": 1.5}
    escriu_atomic(meta_p, json.dumps(meta, separators=(",", ":")))
    print(f"WRF: OK {W}x{H} px, {len(camps)} passos, màxim horari {np.nanmax(R):.1f} mm/h")
    return meta


# ----------------------------------------------------------------------------- AROME (GRIB2, malla regular lat/lon)
RE_AROME = re.compile(r"arome_sfc_(\d{8})_(\d{2})\.grib2$")


def exporta_arome(carpeta, sortida, forca, res_deg, bbox):
    cand = []
    for f in glob.glob(os.path.join(carpeta, "arome_sfc_*.grib2")):
        m = RE_AROME.search(os.path.basename(f))
        if m:
            cand.append((m.group(1) + m.group(2), f))
    if not cand:
        print("AROME: cap fitxer sfc a", carpeta)
        return None
    cod, fitxer = sorted(cand)[-1]
    run = datetime.strptime(cod, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    run_txt = run.strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = Path(sortida) / "arome"
    meta_p = dest / "meta.json"
    if not forca and meta_p.exists():
        try:
            if json.loads(meta_p.read_text()).get("run_utc") == run_txt:
                print(f"AROME: run {run_txt} ja exportat")
                return json.loads(meta_p.read_text())
        except Exception:
            pass
    import eccodes as ec
    acum = {}
    lat1 = lon1 = dlat = dlon = ni = nj = None
    with open(fitxer, "rb") as fh:
        while True:
            h = ec.codes_grib_new_from_file(fh)
            if h is None:
                break
            sn = ec.codes_get(h, "shortName")
            pid = ec.codes_get(h, "paramId")
            if sn in ("tp", "tirf") or pid in (228, 260267):          # precipitació total acumulada
                if lat1 is None:
                    ni, nj = ec.codes_get(h, "Ni"), ec.codes_get(h, "Nj")
                    lat1 = ec.codes_get(h, "latitudeOfFirstGridPointInDegrees")
                    lon1 = ec.codes_get(h, "longitudeOfFirstGridPointInDegrees")
                    dlat = ec.codes_get(h, "jDirectionIncrementInDegrees")
                    dlon = ec.codes_get(h, "iDirectionIncrementInDegrees")
                    if lon1 > 180:
                        lon1 -= 360
                acum[ec.codes_get(h, "endStep")] = np.array(ec.codes_get_values(h), dtype=np.float64).reshape(nj, ni)
            ec.codes_release(h)
    if not acum:
        print("AROME: el GRIB no porta precipitació total (tp). Cal afegir-la al descarregador d'AROME.")
        return None
    passos = sorted(acum)
    from scipy.ndimage import map_coordinates
    s, w, n, e = bbox
    xs, lats, W, H = graella_destinacio(s, w, n, e, res_deg)
    X, Y = np.meshgrid(xs, lats)
    # índexs fraccionaris dins la malla regular (la primera fila és la latitud més alta)
    fx = (X - lon1) / dlon
    fy = (lat1 - Y) / dlat
    ac = [np.clip(acum[p], 0, None) for p in passos]
    hor = [np.zeros_like(ac[0])] + [np.clip(ac[i] - ac[i - 1], 0, None) for i in range(1, len(ac))]
    camps = []
    for h_ in hor:
        v = map_coordinates(h_, [fy, fx], order=1, mode="nearest")
        v[(fy < 0) | (fy > nj - 1) | (fx < 0) | (fx > ni - 1)] = np.nan
        camps.append(v)
    dest.mkdir(parents=True, exist_ok=True)
    escriu_sprite(camps, dest / "precip_h.png")
    meta = {"model": "arome", "nom": "AROME", "run_utc": run_txt, "pas_h": 1, "passos": len(camps),
            "bounds": [[round(s, 4), round(w, 4)], [round(n, 4), round(e, 4)]], "w": W, "h": H, "cols": COLS,
            "escala": ESCALA, "nodata": NODATA, "fitxer": "precip_h.png", "resolucio_km": 2.5}
    escriu_atomic(meta_p, json.dumps(meta, separators=(",", ":")))
    print(f"AROME: OK {W}x{H} px, {len(camps)} passos")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wrf-dir", default="/home/labfire/data/SMC-WRF")
    ap.add_argument("--arome-dir", default="/home/labfire/data/AROME-CAT")
    ap.add_argument("--sortida", default="data/models")
    ap.add_argument("--forca", action="store_true", help="reprocessa encara que el run ja estigui exportat")
    ap.add_argument("--res-wrf", type=float, default=0.0135, help="mida de píxel (graus) de sortida del WRF (~1,5 km)")
    ap.add_argument("--res-arome", type=float, default=0.025)
    ap.add_argument("--bbox-arome", type=float, nargs=4, default=[39.6, -1.4, 43.4, 4.2], metavar=("S", "W", "N", "E"))
    ap.add_argument("--sense-wrf", action="store_true")
    ap.add_argument("--sense-arome", action="store_true")
    a = ap.parse_args()
    Path(a.sortida).mkdir(parents=True, exist_ok=True)
    models = []
    if not a.sense_wrf:
        try:
            m = exporta_wrf(a.wrf_dir, a.sortida, a.forca, a.res_wrf)
            if m:
                models.append(m)
        except Exception as ex:
            print("WRF: error:", repr(ex))
    if not a.sense_arome:
        try:
            m = exporta_arome(a.arome_dir, a.sortida, a.forca, a.res_arome, a.bbox_arome)
            if m:
                models.append(m)
        except Exception as ex:
            print("AROME: error:", repr(ex))
    # índex (només els models que tenen dades)
    escriu_atomic(Path(a.sortida) / "index.json", json.dumps({"models": [{"model": m["model"], "nom": m["nom"], "run_utc": m["run_utc"]} for m in models]},
                                                            separators=(",", ":")))
    print("índex:", [m["model"] for m in models])


if __name__ == "__main__":
    main()
