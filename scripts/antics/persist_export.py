#!/usr/bin/env python3
"""
Exporta per al visor la persistència de precipitació intensa (compost AEMET).

Escriu a --sortida (p.ex. ~/echotops-viewer/data/persist/):
  meta.json        final de finestra, límits Leaflet [[S,W],[N,E]], mida graella, paràmetres
  ratxa_3h.png ... PNG RGBA retallats (només píxels amb ratxa >= --min-ratxa) per a l'overlay
  episodis.json    per píxel "fila,col": llista d'episodis [inici_min, durada_min, classe_max, mm, en_curs]
                   (inici_min = minuts des de `t0`; només episodis amb durada >= --min-ratxa)

Pensat per córrer al cron DESPRÉS d'actualitzar l'arxiu de fotogrames (cada 10 min).
"""
import argparse, json, shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

import persist as P

# Retall per defecte: Catalunya + marge  (lon_min, lat_min, lon_max, lat_max)
BBOX_CAT = (-0.3, 40.3, 3.8, 43.1)


def retalla(bounds, bbox, shape):
    """Retorna (r0, r1, c0, c1) i els límits Leaflet del retall, alineats als píxels."""
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


def episodis(cub, ok, llindar, min_dur_min):
    """Episodis (entrades al llindar) per píxel, amb durada, classe màxima i mm acumulats."""
    n, h, w = cub.shape
    mm_h = P.taula_mm_h()
    inici = np.full((h, w), -1, np.int32)
    cmax = np.zeros((h, w), np.uint8)
    mm = np.zeros((h, w), np.float32)
    out = {}

    def tanca(mask, k_final, en_curs):
        ys, xs = np.nonzero(mask)
        for y, x in zip(ys, xs):
            dur = (k_final - inici[y, x]) * P.PAS_MIN
            if dur >= min_dur_min:
                out.setdefault(f"{y},{x}", []).append(
                    [int(inici[y, x]) * P.PAS_MIN, int(dur), int(cmax[y, x]), round(float(mm[y, x]), 1), int(en_curs)])

    for k in range(n):
        if not ok[k]:
            actiu = inici >= 0
            tanca(actiu, k, False)          # un forat talla l'episodi
            inici[actiu] = -1; cmax[actiu] = 0; mm[actiu] = 0
            continue
        cl = cub[k]
        sobre = cl >= llindar
        acaba = (inici >= 0) & ~sobre
        if acaba.any():
            tanca(acaba, k, False)
            inici[acaba] = -1; cmax[acaba] = 0; mm[acaba] = 0
        nou = sobre & (inici < 0)
        inici[nou] = k
        cmax[sobre] = np.maximum(cmax[sobre], cl[sobre])
        mm[sobre] += mm_h[np.minimum(cl[sobre], 12)] * (P.PAS_MIN / 60.0)
    tanca(inici >= 0, n, True)              # episodis encara oberts a l'últim fotograma
    return out


# Nivells d'intensitat: classe mínima -> (etiqueta, minuts continus per considerar persistència)
NIVELLS_DEFECTE = ["5:120", "6:60", "8:30"]
DBZ_INF = {5: 30, 6: 35, 7: 40, 8: 45, 9: 50}   # límit inferior de la classe (dBZ)


def mm_h_dbz(dbz):
    """Intensitat (mm/h) per Z-R Marshall-Palmer al límit inferior de la classe."""
    return (10 ** (dbz / 10.0) / 200.0) ** (1 / 1.6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arrel", default="/home/claude/javimiroo/radar-arxiu/data")
    ap.add_argument("--sortida", default="/home/claude/persistencia/sortida_visor")
    ap.add_argument("--nivells", nargs="+", default=NIVELLS_DEFECTE, metavar="CLASSE:MIN",
                    help="classe mínima i minuts continus, p.ex. 6:60 (classe 6 = >=35 dBZ)")
    ap.add_argument("--hores", type=float, nargs="+", default=[3, 6, 12, 24, 48, 72])
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX_CAT, metavar=("LON0", "LAT0", "LON1", "LAT1"))
    ap.add_argument("--final", help="AAAAMMDDHHMM UTC (per defecte, l'últim fotograma)")
    a = ap.parse_args()
    nivells = [tuple(int(x) for x in n.split(":")) for n in a.nivells]

    arrel = Path(a.arrel)
    frames = P.llista_fotogrames(arrel)
    if not frames:
        raise SystemExit("Cap fotograma trobat")
    fi = datetime.strptime(a.final, "%Y%m%d%H%M").replace(tzinfo=timezone.utc) if a.final else max(frames)
    bounds = json.loads(next(iter(arrel.glob("composit/*/radar_*.json"))).read_text())["bounds"]
    hmax = max(a.hores)

    tmp = Path(str(a.sortida) + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    # Cub de la finestra més llarga; les curtes en són el final
    ts, cub, ok = P.carrega_finestra(frames, fi, hmax)
    (r0, r1, c0, c1), lb = retalla(bounds, a.bbox, cub.shape[1:])
    cub = cub[:, r0:r1, c0:c1]

    meta_nivells, total_px = [], 0
    for cls, min_ratxa in nivells:
        for hores in a.hores:
            n = int(hores * 60 / P.PAS_MIN) + 1
            res = P.calcula(cub[-n:], ok[-n:], cls)
            camp = np.where(res["ratxa_max"] >= min_ratxa, res["ratxa_max"], 0)
            # escala fixa respecte al mínim: mínim (groc) -> 6x el mínim (granat)
            P.png_camp(camp, min_ratxa * 6, tmp / f"ratxa_c{cls}_{int(hores)}h.png")
        ep = episodis(cub, ok, cls, min_ratxa)
        total_px += len(ep)
        (tmp / f"episodis_c{cls}.json").write_text(json.dumps(
            {"t0": ts[0].strftime("%Y-%m-%dT%H:%M:%SZ"), "pas_min": P.PAS_MIN, "ep": ep}, separators=(",", ":")))
        dbz = DBZ_INF.get(cls, 45)
        meta_nivells.append({"classe": cls, "dbz": dbz, "mm_h": round(mm_h_dbz(dbz)),
                             "min_ratxa_min": min_ratxa, "n_pixels": len(ep)})

    (tmp / "meta.json").write_text(json.dumps({
        "final_utc": fi.strftime("%Y-%m-%dT%H:%M:%SZ"), "bounds": lb, "rows": r1 - r0, "cols": c1 - c0,
        "nivells": meta_nivells, "hores": a.hores, "cobertura": float(ok.mean()),
        "escala_classes": "1=5-15dBZ,2=15-20,3=20-25,4=25-30,5=30-35,6=35-40,7=40-45,8=45-50,9=50-55,10=55-60,11=60-65,12=>65",
    }, indent=1))

    # Publicació atòmica: el visor no veu mai un directori a mig escriure
    dest = Path(a.sortida)
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    mida = sum(p.stat().st_size for p in dest.iterdir())
    detall = " | ".join(f"c{n['classe']}: {n['n_pixels']} px" for n in meta_nivells)
    print(f"OK {fi:%Y-%m-%d %H:%M}Z | retall {r1-r0}x{c1-c0} | {detall} | {mida/1024:.0f} KB")


if __name__ == "__main__":
    main()
