#!/usr/bin/env python3
"""Radar OPERA CIRRUS (EUMETNET Open Radar Data, CC BY 4.0): reflectivitat màxima 1 km / 5 min
-> PNG en Web Mercator d'una finestra àmplia (Ibèria oriental + Atlàntic proper + Mediterrani).
Escriu a data/radar_opera/ (hora = fi de l'interval, UTC):
  rf_AAAAMMDD_HHMM.png + refl_meta.json   reflectivitat (dBZ), paleta d'AEMET/França (15-65 dBZ)
  ld_AAAAMMDD_HHMM.png + meta.json        pluja estimada (mm/h, Marshall-Palmer Z = 200 R^1.6), paleta de França
Guarda també el fitxer brut (.h5, dBZ originals) a ~/echotops-data/opera/ (fora de git, últimes 3 h)
per al càlcul de seguiment de tempestes. No necessita cap clau (bucket S3 públic)."""
import json, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np, h5py
from PIL import Image
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "radar_opera"
BRUT = Path.home() / "echotops-data" / "opera"      # .h5 originals (fora del repositori)
S3 = "https://s3.waw3-1.cloudferro.com/openradar-24h"
NMAX = 36                     # fotogrames guardats (36 x 5 min = 3 h, com el radar de França)
W, E, S, N = -12.0, 8.0, 35.0, 47.0     # finestra (graus): ampla, per veure què s'apropa
PX = 1200.0                   # mida de píxel en metres de Mercator
BREAKS = [0.1, 0.2, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 20, 24, 30, 40, 50, 60, 80, 100, 125]   # mm/h
RGB = [(180,215,255), (117,186,255), (53,154,255), (4,130,255), (0,105,210), (0,54,127), (20,143,27), (26,207,5), (99,237,7),
       (255,244,43), (232,220,0), (240,96,0), (255,127,39), (255,166,106), (248,78,120), (247,30,84), (191,0,0), (136,0,0),
       (100,0,127), (194,0,251), (221,102,255), (235,166,255), (249,230,255), (212,212,212), (150,150,150)]
COLS = ["#%02x%02x%02x" % c for c in RGB]
# reflectivitat (mateixa paleta i opacitats que radar_fr_refl_collector.py i AEMET)
Z_LIM = [15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
Z_COL = [(150, 215, 255), (70, 160, 255), (0, 190, 220), (0, 190, 80), (170, 215, 0), (255, 235, 0),
         (255, 150, 0), (240, 40, 20), (170, 0, 30), (210, 0, 170), (150, 60, 220)]
Z_ALFA = [150, 190, 205, 215, 225, 230, 235, 240, 245, 250, 255]

def llista(prefix):
    """Claus del bucket amb aquest prefix (una sola pàgina: n'hi ha ~40 per hora)."""
    url = S3 + "?list-type=2&prefix=" + urllib.parse.quote(prefix, safe="/@")
    xml = urllib.request.urlopen(url, timeout=30).read().decode()
    return re.findall(r"<Key>([^<]+)</Key>", xml)

def descarrega(clau, dest):
    urllib.request.urlretrieve(S3 + "/" + urllib.parse.quote(clau, safe="/@"), dest)

def dbz_a_mmh(z):
    """dBZ -> mm/h (Marshall-Palmer). Valors no vàlids -> 0. Límit a 125 mm/h (evita ecos de calamarsa)."""
    out = np.zeros(z.shape, dtype=np.float32)
    ok = np.isfinite(z) & (z > -100)
    out[ok] = (10 ** (z[ok] / 10.0) / 200.0) ** (1 / 1.6)
    return np.minimum(out, 125.0)

def geometria():
    """Reixa Mercator de sortida: coordenades de cada píxel i límits [[S,W],[N,E]]."""
    t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    ti = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x0, y0 = t.transform(W, S)
    x1, y1 = t.transform(E, N)
    nx, ny = int(round((x1 - x0) / PX)), int(round((y1 - y0) / PX))
    xs = x0 + (np.arange(nx) + 0.5) * PX
    ys = y1 - (np.arange(ny) + 0.5) * PX          # fila 0 = nord
    X, Y = np.meshgrid(xs, ys)
    lon, lat = ti.transform(X, Y)
    w_, s_ = ti.transform(x0, y0)
    e_, n_ = ti.transform(x0 + nx * PX, y0 + ny * PX)
    return lon, lat, [[s_, w_], [n_, e_]]

def mostreja(h5path, lon, lat):
    """Llegeix el compost ODIM i el mostreja a la reixa Mercator de sortida. Retorna dBZ (float32); -999 = sense dades."""
    with h5py.File(h5path, "r") as h:
        ds = h["dataset1/data1/data"]
        wt = h["dataset1/data1/what"].attrs
        gain, off = float(wt["gain"]), float(wt["offset"])
        nodata, undet = float(wt["nodata"]), float(wt["undetect"])
        wh = h["where"].attrs
        pd = wh["projdef"].decode() if isinstance(wh["projdef"], bytes) else str(wh["projdef"])
        xsc, ysc = float(wh["xscale"]), float(wh["yscale"])
        tr = Transformer.from_crs("EPSG:4326", CRS.from_proj4(pd), always_xy=True)
        xul, yul = tr.transform(float(wh["UL_lon"]), float(wh["UL_lat"]))   # centre del píxel (0,0)
        X, Y = tr.transform(lon, lat)
        col = np.rint((X - xul) / xsc).astype(int)
        row = np.rint((yul - Y) / ysc).astype(int)
        ny0, nx0 = ds.shape
        dins = (col >= 0) & (col < nx0) & (row >= 0) & (row < ny0)
        if not dins.any():
            raise RuntimeError("La finestra queda fora de la reixa OPERA")
        r0, r1 = row[dins].min(), row[dins].max() + 1       # llegeixo només el tros necessari
        c0, c1 = col[dins].min(), col[dins].max() + 1
        tros = ds[r0:r1, c0:c1].astype(np.float64)
    bad = (tros == nodata) | (tros == undet)
    z = tros * gain + off
    z[bad] = -999
    out = np.full(lon.shape, -999, dtype=np.float32)
    out[dins] = z[row[dins] - r0, col[dins] - c0]
    return out

def img_pluja(z):
    mm = dbz_a_mmh(z)
    idx = np.digitize(mm, BREAKS)                    # 0 = sota 0,1 mm/h (transparent)
    im = Image.fromarray(idx.astype(np.uint8), "P")
    im.putpalette([0, 0, 0] + [v for c in RGB for v in c])
    im.info["transparency"] = 0
    return im

def img_refl(z):
    idx = np.digitize(z, Z_LIM)                      # 0 = sota 15 dBZ o sense dades (transparent)
    idx[z < -100] = 0
    im = Image.fromarray(idx.astype(np.uint8), "P")
    im.putpalette([0, 0, 0] + [v for c in Z_COL for v in c])
    im.info["transparency"] = bytes([0] + Z_ALFA)    # opacitat per classe
    return im

def escriu_meta(nom_meta, prefix, unitat, font, limits, colors, bounds):
    fets = sorted(p.name for p in DEST.glob(prefix + "_*.png"))
    for vell in fets[:-NMAX]:
        (DEST / vell).unlink()
    fets = fets[-NMAX:]
    frames = [{"t": datetime.strptime(f[3:-4], "%Y%m%d_%H%M").strftime("%Y-%m-%dT%H:%MZ"), "f": f} for f in fets]
    meta = {"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "font": font, "unitat": unitat,
            "bounds": bounds, "limits": limits, "colors": colors, "frames": frames}
    (DEST / nom_meta).write_text(json.dumps(meta))
    return frames

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    BRUT.mkdir(parents=True, exist_ok=True)
    ara = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ara -= timedelta(minutes=ara.minute % 5)
    hores = {(ara - timedelta(minutes=5 * i)).replace(minute=0) for i in range(NMAX + 1)}
    claus = {}
    for h in sorted(hores):
        p = h.strftime("%Y/%m/%d/OPERA/COMP/OPERA@%Y%m%dT%H")
        for k in llista(p):
            m = re.search(r"OPERA@(\d{8}T\d{4})@0@DBZH\.h5$", k)
            if m:
                claus[datetime.strptime(m.group(1), "%Y%m%dT%H%M")] = k
    temps = sorted(claus)[-NMAX:]
    lon, lat, bounds = geometria()
    nous = 0
    for t in temps:
        sufix = f"{t:%Y%m%d_%H%M}"
        rf, ld = DEST / f"rf_{sufix}.png", DEST / f"ld_{sufix}.png"
        brut = BRUT / f"OPERA_{sufix}_DBZH.h5"
        if rf.exists() and ld.exists() and brut.exists():
            continue
        try:
            if not brut.exists():
                tmp = BRUT / "_tmp.h5"
                descarrega(claus[t], tmp)
                tmp.replace(brut)                   # només es queda si la descàrrega ha acabat bé
            if not (rf.exists() and ld.exists()):
                z = mostreja(brut, lon, lat)
                img_refl(z).save(rf, optimize=True)
                img_pluja(z).save(ld, optimize=True)
                nous += 1
                print("OPERA: afegit", sufix)
        except Exception as e:
            print("OPERA: error amb", claus[t], "->", e)
            (BRUT / "_tmp.h5").unlink(missing_ok=True)
    # neteja del brut (3 h) i metadades
    for p in sorted(BRUT.glob("OPERA_*_DBZH.h5"))[:-NMAX]:
        p.unlink()
    escriu_meta("refl_meta.json", "rf", "dBZ",
                "OPERA CIRRUS · EUMETNET (CC BY 4.0) · reflectivitat màxima de 1 km, només ≥ 15 dBZ",
                Z_LIM, ["#%02x%02x%02x" % c for c in Z_COL], bounds)
    fl = escriu_meta("meta.json", "ld", "mm/h",
                     "OPERA CIRRUS · EUMETNET (CC BY 4.0) · mm/h estimats de la reflectivitat (Marshall-Palmer)",
                     BREAKS, COLS, bounds)
    if not fl:
        print("OPERA: cap fotograma"); return 1
    print(f"OPERA: {nous} nous, {len(fl)} en total, últim {fl[-1]['t']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
