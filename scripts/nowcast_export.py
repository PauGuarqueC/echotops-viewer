#!/usr/bin/env python3
"""
Exporta per al visor les tempestes "enganxades" detectades a l'últim fotograma del compost AEMET.

Escriu a --sortida (p.ex. data/nowcast/):  (+ historial.json i refl/ amb les imatges de reflectivitat)
  avisos.json   instant de les dades, límits del retall i llista de cel·les amb nivell d'avís

Nivells (sobre cel·les amb classe >= --llindar i àrea >= --min-px):
  1 Vigilància : enganxada >= 30 min
  2 Atenció    : enganxada >= 90 min i ~20 mm o més de mitjana des que s'hi ha parat
  3 Alerta     : enganxada >= 120 min i ~40 mm o més de mitjana
"""
import argparse, json, shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import persist as P
import nowcast as N

# Retall per defecte: Catalunya + marge  (lon_min, lat_min, lon_max, lat_max)
BBOX_CAT = (-0.3, 40.3, 3.8, 43.1)


def retalla(bounds, bbox, shape):
    """Retorna (r0, r1, c0, c1) i els límits Leaflet [[S,W],[N,E]] del retall, alineats als píxels."""
    h, w = shape
    lon0, lat0, lon1, lat1 = bounds["lon_min"], bounds["lat_min"], bounds["lon_max"], bounds["lat_max"]
    dlon, dlat = (lon1 - lon0) / w, (lat1 - lat0) / h
    c0 = max(0, int(np.floor((bbox[0] - lon0) / dlon)))
    c1 = min(w, int(np.ceil((bbox[2] - lon0) / dlon)))
    r0 = max(0, int(np.floor((lat1 - bbox[3]) / dlat)))
    r1 = min(h, int(np.ceil((lat1 - bbox[1]) / dlat)))
    s = lat1 - r1 * dlat
    n = lat1 - r0 * dlat
    west = lon0 + c0 * dlon
    east = lon0 + c1 * dlon
    return (r0, r1, c0, c1), [[round(s, 5), round(west, 5)], [round(n, 5), round(east, 5)]]

ESCALA = 4   # píxels de PNG per píxel de radar
COLORS = {1: (255, 200, 0, 255), 2: (255, 120, 0, 255), 3: (230, 20, 40, 255)}
# Reflectivitat: classe -> RGBA (1 = 5-15 dBZ, 12 = >65 dBZ); 0 i 255 (sense dada) transparents
REFL = {1: (0, 0, 0, 0), 2: (150, 215, 255, 150), 3: (70, 160, 255, 190), 4: (0, 190, 220, 205), 5: (0, 190, 80, 215),
        6: (170, 215, 0, 225), 7: (255, 235, 0, 230), 8: (255, 150, 0, 235), 9: (240, 40, 20, 240),
        10: (170, 0, 30, 245), 11: (210, 0, 170, 250), 12: (150, 60, 220, 255)}
ESCALA_REFL = 3
NOMS = {1: "Vigilància", 2: "Atenció", 3: "Alerta"}


def distancia_costa(lb, H, W, cache):
    """Matriu (H,W) amb els km fins al píxel de terra més proper (0 a terra). None si no es pot calcular.
    Es calcula una vegada amb la màscara terra/mar del paquet `global-land-mask` i es desa a `cache`."""
    s, w = lb[0]
    n, e = lb[1]
    clau = np.array([s, w, n, e, H, W], float)
    cache = Path(cache)
    try:
        if cache.exists():
            z = np.load(cache)
            if z["clau"].shape == clau.shape and np.allclose(z["clau"], clau):
                return z["dist"]
    except Exception:
        pass
    try:
        from global_land_mask import globe
    except ImportError:
        print("AVÍS: falta 'global-land-mask' (pip install global-land-mask): no es distingeix mar de terra")
        return None
    sub = 3
    lats = n - (np.arange(H * sub) + 0.5) / (H * sub) * (n - s)
    lons = w + (np.arange(W * sub) + 0.5) / (W * sub) * (e - w)
    terra_fina = globe.is_land(lats[:, None], lons[None, :])
    terra = terra_fina.reshape(H, sub, W, sub).mean(axis=(1, 3)) >= 0.25      # píxel costaner = terra
    km_y = (n - s) / H * 111.2
    km_x = (e - w) / W * 111.2 * np.cos(np.radians((n + s) / 2))
    dist = ndimage.distance_transform_edt(~terra, sampling=(km_y, km_x)).astype(np.float32)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, clau=clau, dist=dist)
    except Exception as ex:
        print("AVÍS: no s'ha pogut desar la màscara de costa:", ex)
    return dist


def nivell(a):
    d, mm = a["enganxada_min"], a["mm_mitjana"]
    if d >= 120 and mm >= 40:
        return 3
    if d >= 90 and mm >= 20:
        return 2
    if d >= 30:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arrel", default="/home/claude/javimiroo/radar-arxiu/data")
    ap.add_argument("--sortida", default="/home/claude/persistencia/sortida_nowcast")
    ap.add_argument("--llindar", type=int, default=6, help="classe mínima (6 = >=35 dBZ)")
    ap.add_argument("--min-px", type=int, default=12, help="àrea mínima en píxels de radar (~6,9 km2 cadascun)")
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX_CAT, metavar=("LON0", "LAT0", "LON1", "LAT1"))
    ap.add_argument("--historial", type=float, default=48, help="hores d'historial a calcular (0 = només l'últim)")
    ap.add_argument("--no-refl", action="store_true", help="no genera les imatges de reflectivitat")
    ap.add_argument("--dist-costa", type=float, default=20,
                    help="km: cel·les a més d'aquesta distància de la terra es marquen com a 'mar' i no fan avís")
    ap.add_argument("--cache-costa", default=str(Path.home() / "echotops-data" / "dist_costa.npz"))
    ap.add_argument("--final", help="AAAAMMDDHHMM UTC (per defecte, l'últim fotograma)")
    a = ap.parse_args()

    arrel = Path(a.arrel)
    frames = P.llista_fotogrames(arrel)
    if not frames:
        raise SystemExit("Cap fotograma trobat")
    fi = datetime.strptime(a.final, "%Y%m%d%H%M").replace(tzinfo=timezone.utc) if a.final else max(frames)
    bounds = json.loads(next(iter(arrel.glob("composit/*/radar_*.json"))).read_text())["bounds"]

    ts, cub, ok = P.carrega_finestra(frames, fi, 4.5 + a.historial)   # 4,5 h extra: cobreix 240 min d'enganxament
    (r0, r1, c0, c1), lb = retalla(bounds, a.bbox, cub.shape[1:])
    cub = cub[:, r0:r1, c0:c1]
    k = len(ts) - 1
    if not ok[k]:
        raise SystemExit(f"Falta el fotograma de {fi:%Y-%m-%d %H:%MZ}")
    (s, w), (n, e) = lb
    H, W = cub.shape[1:]
    mm_h = P.taula_mm_h()
    dist_costa = distancia_costa(lb, H, W, a.cache_costa)

    def avisos_fotograma(k):
        """Cel·les amb nivell >= 1 a l'índex k (amb màscara)."""
        res = []
        for av in N.detecta(cub, ok, k, llindar=a.llindar, min_px=a.min_px, max_min=240):
            niv = nivell(av)
            if niv == 0:
                continue
            mask = av["mask"]
            mmh_ara = float(mm_h[np.minimum(cub[k][mask], 12)].mean())
            ys, xs = np.nonzero(mask)
            d_costa = float(dist_costa[mask].min()) if dist_costa is not None else 0.0
            av.update({
                "dist_costa_km": round(d_costa), "mar": bool(d_costa > a.dist_costa),
                "nivell": niv, "nom": NOMS[niv],
                "lat": round(n - (av["cy"] + 0.5) / H * (n - s), 4),
                "lon": round(w + (av["cx"] + 0.5) / W * (e - w), 4),
                "area_km2": round(av["area_px"] * 6.9),
                "mm_mitjana": round(av["mm_mitjana"]), "mm_max": round(av["mm_max"]),
                "mm_h_ara": round(mmh_ara, 1),
                "bbox": [[round(n - (ys.max() + 1) / H * (n - s), 4), round(w + xs.min() / W * (e - w), 4)],
                         [round(n - ys.min() / H * (n - s), 4), round(w + (xs.max() + 1) / W * (e - w), 4)]],
            })
            res.append(av)
        res.sort(key=lambda c: (-c["nivell"], -c["enganxada_min"]))
        return res

    # --- últim fotograma: JSON complet (el visor dibuixa quadrats a partir del bbox)
    cel_les = []
    for av in avisos_fotograma(k):
        av.pop("mask")
        for kk in ("cy", "cx", "area_px"):
            av.pop(kk, None)
        cel_les.append(av)

    # --- historial compacte: per fotograma, files [nivell, lat, lon, km2, enganxada, classe, mm_mitj, mm_max, mm_h, s, w, n, e]
    hist = {}
    sense = []
    for kk in range(k + 1):
        if (fi - ts[kk]).total_seconds() > a.historial * 3600:
            continue
        if not ok[kk]:
            sense.append(ts[kk].strftime("%Y%m%d%H%M"))
            continue
        files = []
        for av in avisos_fotograma(kk):
            (bs, bw), (bn, be) = av["bbox"]
            files.append([av["nivell"], av["lat"], av["lon"], av["area_km2"], av["enganxada_min"], av["classe_max"],
                          av["mm_mitjana"], av["mm_max"], av["mm_h_ara"], bs, bw, bn, be, av["dist_costa_km"]])
        if files:
            hist[ts[kk].strftime("%Y%m%d%H%M")] = files

    tmp = Path(str(a.sortida) + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    # --- Imatges de reflectivitat per fotograma (incremental: només les que falten; es conserven entre execucions)
    if not a.no_refl:
        dest_refl = Path(a.sortida) / "refl"
        if dest_refl.exists():
            shutil.move(str(dest_refl), str(tmp / "refl"))
        refl = tmp / "refl"
        refl.mkdir(exist_ok=True)
        lut = np.zeros((256, 4), np.uint8)
        for c, rgba in REFL.items():
            lut[c] = rgba
        clau_min = (fi - timedelta(hours=a.historial)).strftime("%Y%m%d%H%M")
        for kk in range(len(ts)):
            clau = ts[kk].strftime("%Y%m%d%H%M")
            if clau < clau_min or not ok[kk] or (refl / f"{clau}.png").exists():
                continue
            cl = np.kron(cub[kk], np.ones((ESCALA_REFL, ESCALA_REFL), np.uint8))
            Image.fromarray(lut[cl], "RGBA").save(refl / f"{clau}.png", optimize=True)
        for f in refl.glob("*.png"):          # neteja el que surt de la finestra
            if f.stem < clau_min:
                f.unlink()
    (tmp / "avisos.json").write_text(json.dumps({
        "final_utc": fi.strftime("%Y-%m-%dT%H:%M:%SZ"), "bounds": lb,
        "parametres": {"llindar_classe": a.llindar, "min_area_km2": round(a.min_px * 6.9),
                       "dist_costa_km": a.dist_costa},
        "cel_les": cel_les,
    }, separators=(",", ":")))
    (tmp / "historial.json").write_text(json.dumps({
        "final_utc": fi.strftime("%Y-%m-%dT%H:%M:%SZ"), "pas_min": P.PAS_MIN, "hores": a.historial,
        "sense_dades": sense, "fotogrames": hist,
        "columnes": ["nivell", "lat", "lon", "area_km2", "enganxada_min", "classe_max", "mm_mitjana", "mm_max", "mm_h_ara", "s", "w", "n", "e", "dist_costa_km"],
    }, separators=(",", ":")))
    dest = Path(a.sortida)
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    per_niv = {i: sum(1 for c in cel_les if c["nivell"] == i and not c["mar"]) for i in (1, 2, 3)}
    n_mar = sum(1 for c in cel_les if c["mar"])
    print(f"OK {fi:%Y-%m-%d %H:%M}Z | cel·les enganxades: vigilància {per_niv[1]}, atenció {per_niv[2]}, alerta {per_niv[3]} | a mar (sense avís): {n_mar}")


if __name__ == "__main__":
    main()
