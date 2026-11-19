#!/usr/bin/env python3
"""
Descarrega el compost de radar AEMET (tota Espanya) i l'arxiva en local, sense dependre de cap altre repositori.

Font (sense clau d'API): https://www.aemet.es/en/api-eltiempo/radar/download/compo
  -> un .tar amb els últims fotogrames (GeoTIFF, una banda amb classes 0-12 de reflectivitat).

Escriu a --sortida el mateix format que feia servir l'arxiu extern, de manera que persist.llista_fotogrames()
i nowcast_export.py hi treballen sense canvis:
  <sortida>/composit/AAAAMMDD/radar_AAAAMMDDHHMMSS.npz   (clau 'data', uint8 [files, columnes])
  <sortida>/composit/AAAAMMDD/radar_AAAAMMDDHHMMSS.json  (instant UTC, límits, mida)

Només descarrega/escriu els fotogrames que falten i esborra els dies més antics que --conserva-dies.
La neteja d'interferències (píxels aïllats i línies radials) segueix el mateix criteri que l'arxiu extern.
"""
import argparse, io, json, re, shutil, sys, tarfile, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy import ndimage
import rasterio
from rasterio.io import MemoryFile

URL = "https://www.aemet.es/en/api-eltiempo/radar/download/compo"
HEADERS = {"User-Agent": "GRAFRadarBot/1.0", "Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
ESP_LON = (-9.5, 4.5)
ESP_LAT = (35.5, 44.0)


def baixa(url, intents=3):
    ultim = None
    for i in range(intents):
        try:
            req = urllib.request.Request(f"{url}?_nocache={int(time.time())}", headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            ultim = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"no s'ha pogut baixar {url}: {ultim}")


def retalla(banda, ds, lon=ESP_LON, lat=ESP_LAT):
    b = ds.bounds
    w, h = ds.width, ds.height
    c0 = max(0, int((lon[0] - b.left) / (b.right - b.left) * w))
    c1 = min(w, int((lon[1] - b.left) / (b.right - b.left) * w))
    r0 = max(0, int((b.top - lat[1]) / (b.top - b.bottom) * h))
    r1 = min(h, int((b.top - lat[0]) / (b.top - b.bottom) * h))
    bounds = {"lon_min": b.left + c0 * (b.right - b.left) / w, "lat_min": b.top - r1 * (b.top - b.bottom) / h,
              "lon_max": b.left + c1 * (b.right - b.left) / w, "lat_max": b.top - r0 * (b.top - b.bottom) / h}
    return banda[r0:r1, c0:c1].copy(), bounds


def neteja_interferencies(classes, min_area=1):
    """Treu píxels aïllats, línies fines i llargues (radials RF) i components esquelètics."""
    lab, n = ndimage.label(classes > 0, structure=np.ones((3, 3)))
    if n == 0:
        return classes
    objs = ndimage.find_objects(lab)
    mides = ndimage.sum(classes > 0, lab, range(1, n + 1))
    treu = np.zeros(n + 1, bool)
    for i, sl in enumerate(objs, start=1):
        area = mides[i - 1]
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if area <= min_area or (max(h, w) >= 6 and min(h, w) <= 2) or (max(h, w) >= 8 and area / (h * w) < 0.15):
            treu[i] = True
    out = classes.copy()
    out[treu[lab]] = 0
    return out


def ts_de_nom(nom):
    m = re.search(r"(\d{12,14})", nom)
    if not m:
        return None
    ts = m.group(1)
    return ts + "00" if len(ts) == 12 else ts


def desa(sortida, ts, arr, bounds):
    dia = sortida / "composit" / ts[:8]
    dia.mkdir(parents=True, exist_ok=True)
    base = dia / f"radar_{ts}"
    tmp_npz = dia / f".tmp_radar_{ts}.npz"
    np.savez_compressed(tmp_npz, data=arr)
    meta = {"timestamp_utc": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:00Z", "tipus": "composit_espanya",
            "bounds": bounds, "shape": list(arr.shape), "max_val": int(arr.max()), "px_actius": int((arr > 0).sum())}
    (dia / f".tmp_radar_{ts}.json").write_text(json.dumps(meta, indent=2))
    # el .json va l'últim perquè un fotograma només "existeixi" quan l'npz ja és complet
    tmp_npz.rename(base.with_suffix(".npz"))
    (dia / f".tmp_radar_{ts}.json").rename(base.with_suffix(".json"))


def neteja_antics(sortida, dies):
    tall = (datetime.now(timezone.utc) - timedelta(days=dies)).strftime("%Y%m%d")
    n = 0
    for d in (sortida / "composit").glob("[0-9]" * 8):
        if d.name < tall:
            shutil.rmtree(d)
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortida", required=True, help="carpeta de l'arxiu (p.ex. ~/echotops-data/aemet)")
    ap.add_argument("--conserva-dies", type=int, default=5)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--tar", help="fitxer .tar local en lloc de baixar-lo (proves)")
    a = ap.parse_args()
    sortida = Path(a.sortida)

    try:
        raw = Path(a.tar).read_bytes() if a.tar else baixa(a.url)
        tf = tarfile.open(fileobj=io.BytesIO(raw))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    nous = saltats = 0
    for membre in sorted(tf.getmembers(), key=lambda m: m.name):
        ts = ts_de_nom(membre.name)
        if not ts or not membre.isfile():
            continue
        if (sortida / "composit" / ts[:8] / f"radar_{ts}.json").exists():
            saltats += 1
            continue
        try:
            with MemoryFile(tf.extractfile(membre).read()) as mf, mf.open() as ds:
                arr, bounds = retalla(ds.read(1).astype(np.uint8), ds)
            if arr.ndim != 2 or min(arr.shape) < 100 or arr.max() > 13:
                print(f"AVÍS: {membre.name} té un format inesperat {arr.shape} max={arr.max()}; s'omet", file=sys.stderr)
                continue
            desa(sortida, ts, neteja_interferencies(arr), bounds)
            nous += 1
        except Exception as e:
            print(f"AVÍS: {membre.name}: {e}", file=sys.stderr)
    esborrats = neteja_antics(sortida, a.conserva_dies)
    total = len(list((sortida / "composit").glob("*/radar_*.npz")))
    print(f"OK compost AEMET: {nous} nous, {saltats} ja existents, {total} a l'arxiu" + (f", {esborrats} dies antics esborrats" if esborrats else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
