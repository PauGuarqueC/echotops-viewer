#!/usr/bin/env python3
"""OPERA CIRRUS (1 km) -> arxiu de fotogrames de classes de reflectivitat, a la resolució NATIVA d'OPERA.

Per a cada franja de --pas minuts (10 per defecte) agafa el fitxer brut d'OPERA (~/echotops-data/opera/ o, si no hi
és, el baixa del bucket públic), el porta a una reixa lat/lon de ~1 km x 1 km sobre --domini (sense agregar: cada
píxel és la mostra d'OPERA més propera), el converteix a classes 0-12 i el desa en el mateix format que feia servir
el nowcast (persist.py / nowcast_export.py):
  <sortida>/grid.json                                   límits i mida de la reixa (es crea el primer cop)
  <sortida>/composit/AAAAMMDD/radar_AAAAMMDDHHMM00.npz  (+ .json amb els límits)

Classes:  0 sense eco (< 5 dBZ)   1 = 5-15 dBZ   2 = 15-20 ... 6 = 35-40 ... 11 = 60-65   12 = >= 65 dBZ

Fotograma amb forat de dades: si més d'--max-nodata de l'àrea d'interès (--bbox) és 'sense dades', NO s'escriu; per
al seguiment és un fotograma que falta (el nowcast tolera fins a 2 fotogrames seguits que faltin).
No necessita cap clau (bucket S3 públic) ni res d'AEMET."""
import argparse, json, re, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import opera_collector as OC      # llista(), descarrega(), mostreja(), BRUT

DOMINI = (-2.0, 39.5, 5.0, 44.0)         # (lon0, lat0, lon1, lat1) de l'arxiu: Catalunya + marge ample
BBOX_CAT = (-0.3, 40.3, 3.8, 43.1)       # zona on es vigila que no hi hagi forats de dades
KM_GRAU = 111.2                          # km per grau de latitud


def reixa(domini):
    """Reixa lat/lon de ~1 km: pas en latitud = 1 km, pas en longitud = 1 km a la latitud central."""
    lon0, lat0, lon1, lat1 = domini
    dlat = 1.0 / KM_GRAU
    dlon = dlat / np.cos(np.radians((lat0 + lat1) / 2))
    H = int(round((lat1 - lat0) / dlat))
    W = int(round((lon1 - lon0) / dlon))
    return {"bounds": {"lon_min": lon0, "lat_min": lat0, "lon_max": lon1, "lat_max": lat1}, "shape": [H, W]}


def grid_ref(sortida, domini):
    g = sortida / "grid.json"
    nova = reixa(domini)
    if g.exists():
        vella = json.loads(g.read_text())
        if vella != nova:
            raise SystemExit(f"{g} ja existeix amb un altre domini/mida ({vella}). Si vols canviar el domini, "
                             f"esborra'n el contingut (composit/, sense_dades/ i grid.json) i regenera l'arxiu.")
        return vella
    sortida.mkdir(parents=True, exist_ok=True)
    g.write_text(json.dumps(nova, indent=2))
    print("Reixa creada:", nova["shape"], nova["bounds"])
    return nova


def centres(grid):
    b = grid["bounds"]
    H, W = grid["shape"]
    lat = b["lat_max"] - (np.arange(H) + 0.5) / H * (b["lat_max"] - b["lat_min"])
    lon = b["lon_min"] + (np.arange(W) + 0.5) / W * (b["lon_max"] - b["lon_min"])
    return np.meshgrid(lon, lat)


def classes(z):
    c = np.zeros(z.shape, np.uint8)
    c[(z >= 5) & (z < 15)] = 1
    ok = z >= 15
    c[ok] = np.minimum(2 + (z[ok] - 15) // 5, 12).astype(np.uint8)
    return c


def neteja(c):
    """Treu soroll aïllat a 1 km: taques de menys de 7 píxels (~7 km2), i línies fines i llargues (radials RF).
    Els llindars són els d'AEMET (píxels de ~2,6 km) multiplicats per 2,6 perquè siguin els mateixos en km."""
    lab, n = ndimage.label(c > 0, structure=np.ones((3, 3)))
    if n == 0:
        return c
    objs = ndimage.find_objects(lab)
    mides = ndimage.sum(c > 0, lab, range(1, n + 1))
    treu = np.zeros(n + 1, bool)
    for i, sl in enumerate(objs, start=1):
        area = mides[i - 1]
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if area < 7 or (max(h, w) >= 16 and min(h, w) <= 5) or (max(h, w) >= 21 and area / (h * w) < 0.15):
            treu[i] = True
    out = c.copy()
    out[treu[lab]] = 0
    return out


def desa(sortida, ts, arr, bounds):
    dia = sortida / "composit" / ts[:8]
    dia.mkdir(parents=True, exist_ok=True)
    base = dia / f"radar_{ts}"
    tmp_npz = dia / f".tmp_radar_{ts}.npz"
    np.savez_compressed(tmp_npz, data=arr)
    meta = {"timestamp_utc": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:00Z", "tipus": "opera_1km",
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


def converteix(h5, lonlat, bbox, max_nodata, fer_neteja):
    """Retorna (classes, fraccio_sense_dades) o (None, fraccio) si el fotograma s'ha de descartar."""
    lon, lat = lonlat
    z = OC.mostreja(h5, lon, lat)                    # dBZ; -500 = cobertura sense eco; -999 = sense cobertura
    dins = (lon >= bbox[0]) & (lon <= bbox[2]) & (lat >= bbox[1]) & (lat <= bbox[3])
    frac = float((z[dins] < -900).mean()) if dins.any() else 0.0
    if frac > max_nodata:
        return None, frac
    arr = classes(z)
    return (neteja(arr) if fer_neteja else arr), frac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortida", default=str(Path.home() / "echotops-data" / "opera_1km"))
    ap.add_argument("--brut", default=str(OC.BRUT))
    ap.add_argument("--hores", type=float, default=3, help="franja enrere a revisar (24 = omple tot el bucket)")
    ap.add_argument("--pas", type=int, default=10, help="minuts entre fotogrames (10 evita els forats dels :x5)")
    ap.add_argument("--domini", type=float, nargs=4, default=DOMINI, metavar=("LON0", "LAT0", "LON1", "LAT1"),
                    help="àrea que es desa a l'arxiu")
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX_CAT, metavar=("LON0", "LAT0", "LON1", "LAT1"),
                    help="àrea on es comprova que no hi hagi forats de dades")
    ap.add_argument("--max-nodata", type=float, default=0.10, help="fracció màxima de l'àrea sense dades abans de descartar")
    ap.add_argument("--conserva-dies", type=int, default=5)
    ap.add_argument("--no-neteja", action="store_true", help="no treu soroll aïllat ni línies fines")
    a = ap.parse_args()
    sortida, brut = Path(a.sortida), Path(a.brut)
    grid = grid_ref(sortida, a.domini)
    lonlat = centres(grid)
    marques = sortida / "sense_dades"
    marques.mkdir(parents=True, exist_ok=True)

    ara = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ara -= timedelta(minutes=ara.minute % a.pas)
    franges = []
    t = ara
    while (ara - t).total_seconds() <= a.hores * 3600:
        ts = t.strftime("%Y%m%d%H%M") + "00"
        if not (sortida / "composit" / ts[:8] / f"radar_{ts}.json").exists() and not (marques / ts).exists():
            franges.append(t)
        t -= timedelta(minutes=a.pas)
    franges.sort()
    claus = {}
    nous = descartats = 0
    for t in franges:
        ts = t.strftime("%Y%m%d%H%M") + "00"
        local = brut / f"OPERA_{t:%Y%m%d_%H%M}_DBZH.h5"
        tmp = None
        try:
            if local.exists():
                h5 = local
            else:
                if not claus:
                    hores = {(x.replace(minute=0)) for x in franges}
                    for h in sorted(hores):
                        for k in OC.llista(h.strftime("%Y/%m/%d/OPERA/COMP/OPERA@%Y%m%dT%H")):
                            m = re.search(r"OPERA@(\d{8}T\d{4})@0@DBZH\.h5$", k)
                            if m:
                                claus[datetime.strptime(m.group(1), "%Y%m%dT%H%M").replace(tzinfo=timezone.utc)] = k
                    claus["_"] = True
                if t not in claus:
                    continue                          # encara no publicat (o fora del cache de 24 h)
                tmp = Path(tempfile.mkdtemp()) / "opera.h5"
                OC.descarrega(claus[t], tmp)
                h5 = tmp
            arr, frac = converteix(h5, lonlat, a.bbox, a.max_nodata, not a.no_neteja)
            if arr is None:
                (marques / ts).write_text(f"{frac:.2f}\n")
                descartats += 1
                print(f"OPERA 1 km: {t:%Y-%m-%d %H:%M}Z DESCARTAT, {100 * frac:.0f}% de l'àrea sense dades")
            else:
                desa(sortida, ts, arr, grid["bounds"])
                nous += 1
                print(f"OPERA 1 km: {t:%Y-%m-%d %H:%M}Z ok, {100 * frac:.0f}% de l'àrea sense dades")
        except Exception as e:
            print(f"OPERA 1 km: error amb {t:%H:%M}Z: {e}", file=sys.stderr)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
                tmp.parent.rmdir()
    esb = neteja_antics(sortida, a.conserva_dies)
    total = len(list((sortida / "composit").glob("*/radar_*.npz")))
    print(f"OK OPERA 1 km: {nous} nous, {descartats} descartats per forat de dades, {total} a l'arxiu"
          + (f", {esb} dies antics esborrats" if esb else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
