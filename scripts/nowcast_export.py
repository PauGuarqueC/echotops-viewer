#!/usr/bin/env python3
"""
Exporta per al visor les tempestes "enganxades" detectades a l'últim fotograma del compost AEMET.

Escriu a --sortida (p.ex. data/nowcast/):
  avisos.json   instant de les dades, límits del retall i llista de cel·les amb nivell d'avís
  avisos.png    contorns de les cel·les (RGBA, ampliat x4) per pintar-los sobre el mapa

Nivells (sobre cel·les amb classe >= --llindar i àrea >= --min-px):
  1 Vigilància : enganxada >= 40 min
  2 Atenció    : enganxada >= 90 min i ~20 mm o més de mitjana des que s'hi ha parat
  3 Alerta     : enganxada >= 120 min i ~40 mm o més de mitjana
"""
import argparse, json, shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import persist as P
import nowcast as N
from persist_export import retalla, BBOX_CAT

ESCALA = 4   # píxels de PNG per píxel de radar
COLORS = {1: (255, 200, 0, 255), 2: (255, 120, 0, 255), 3: (230, 20, 40, 255)}
NOMS = {1: "Vigilància", 2: "Atenció", 3: "Alerta"}


def nivell(a):
    d, mm = a["enganxada_min"], a["mm_mitjana"]
    if d >= 120 and mm >= 40:
        return 3
    if d >= 90 and mm >= 20:
        return 2
    if d >= 40:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arrel", default="/home/claude/javimiroo/radar-arxiu/data")
    ap.add_argument("--sortida", default="/home/claude/persistencia/sortida_nowcast")
    ap.add_argument("--llindar", type=int, default=6, help="classe mínima (6 = >=35 dBZ)")
    ap.add_argument("--min-px", type=int, default=12, help="àrea mínima en píxels de radar (~6,9 km2 cadascun)")
    ap.add_argument("--bbox", type=float, nargs=4, default=BBOX_CAT, metavar=("LON0", "LAT0", "LON1", "LAT1"))
    ap.add_argument("--final", help="AAAAMMDDHHMM UTC (per defecte, l'últim fotograma)")
    a = ap.parse_args()

    arrel = Path(a.arrel)
    frames = P.llista_fotogrames(arrel)
    if not frames:
        raise SystemExit("Cap fotograma trobat")
    fi = datetime.strptime(a.final, "%Y%m%d%H%M").replace(tzinfo=timezone.utc) if a.final else max(frames)
    bounds = json.loads(next(iter(arrel.glob("composit/*/radar_*.json"))).read_text())["bounds"]

    ts, cub, ok = P.carrega_finestra(frames, fi, 4.5)       # 4,5 h enrere: cobreix 240 min d'enganxament
    (r0, r1, c0, c1), lb = retalla(bounds, a.bbox, cub.shape[1:])
    cub = cub[:, r0:r1, c0:c1]
    k = len(ts) - 1
    if not ok[k]:
        raise SystemExit(f"Falta el fotograma de {fi:%Y-%m-%d %H:%MZ}")
    (s, w), (n, e) = lb
    H, W = cub.shape[1:]
    mm_h = P.taula_mm_h()

    cel_les = []
    img = np.zeros((H * ESCALA, W * ESCALA, 4), np.uint8)
    for av in N.detecta(cub, ok, k, llindar=a.llindar, min_px=a.min_px, max_min=240):
        niv = nivell(av)
        if niv == 0:
            continue
        mask = av.pop("mask")
        # intensitat actual (mm/h mitjana a la cel·la) -> "si es manté, ~X mm en 1 h"
        cl_ara = cub[k][mask]
        mmh_ara = float(mm_h[np.minimum(cl_ara, 12)].mean())
        ys, xs = np.nonzero(mask)
        cel_les.append({
            "nivell": niv, "nom": NOMS[niv],
            "lat": round(n - (av["cy"] + 0.5) / H * (n - s), 4),
            "lon": round(w + (av["cx"] + 0.5) / W * (e - w), 4),
            "area_km2": round(av["area_px"] * 6.9),
            "enganxada_min": av["enganxada_min"],
            "classe_max": av["classe_max"],
            "mm_mitjana": round(av["mm_mitjana"]), "mm_max": round(av["mm_max"]),
            "mm_h_ara": round(mmh_ara, 1),
            "bbox": [[round(n - (ys.max() + 1) / H * (n - s), 4), round(w + xs.min() / W * (e - w), 4)],
                     [round(n - ys.min() / H * (n - s), 4), round(w + (xs.max() + 1) / W * (e - w), 4)]],
        })
        m4 = np.kron(mask, np.ones((ESCALA, ESCALA), bool))
        vora = m4 & ~ndimage.binary_erosion(m4, iterations=2)
        img[vora] = COLORS[niv]
    cel_les.sort(key=lambda c: (-c["nivell"], -c["enganxada_min"]))

    tmp = Path(str(a.sortida) + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    Image.fromarray(img, "RGBA").save(tmp / "avisos.png")
    (tmp / "avisos.json").write_text(json.dumps({
        "final_utc": fi.strftime("%Y-%m-%dT%H:%M:%SZ"), "bounds": lb,
        "parametres": {"llindar_classe": a.llindar, "min_area_km2": round(a.min_px * 6.9)},
        "cel_les": cel_les,
    }, separators=(",", ":")))
    dest = Path(a.sortida)
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    per_niv = {i: sum(1 for c in cel_les if c["nivell"] == i) for i in (1, 2, 3)}
    print(f"OK {fi:%Y-%m-%d %H:%M}Z | cel·les enganxades: vigilància {per_niv[1]}, atenció {per_niv[2]}, alerta {per_niv[3]}")


if __name__ == "__main__":
    main()
