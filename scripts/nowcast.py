#!/usr/bin/env python3
"""
Detector de tempestes "enganxades" (quasi-estacionàries) sobre el compost de radar AEMET.

Idea: per a cada cel·la intensa ACTUAL (component connex amb classe >= llindar), es mira quant de
temps enrere ha estat la seva mateixa àrea per sobre del llindar. Una cel·la que es mou deixa
l'àrea en poc temps (solapament amb el passat cau ràpid); una cel·la enganxada conserva l'àrea.

  solapament(tau) = |cel·la ara  ∩  àrea intensa fa tau min| / |cel·la ara|
  durada_enganxada = tau més llarg tal que el solapament es manté >= --solap per a tots els tau' <= tau

Sortida per instant: llista d'avisos amb posició, àrea, durada enganxada, intensitat màxima i mm
acumulats a la cel·la des que s'hi ha enganxat.
"""
import numpy as np
from scipy import ndimage

import persist as P

PAS = P.PAS_MIN
ESTRUCT8 = np.ones((3, 3), bool)
MAX_BUITS = 2     # fotogrames seguits que poden faltar sense trencar l'enganxament ni el càlcul de velocitat


def mascares(cub, ok, llindar):
    """Màscara booleana per fotograma (False on el fotograma falta)."""
    m = (cub >= llindar) & (cub != 255)
    m[~ok] = False
    return m


def cel_les(m_ara, min_px):
    lab, n = ndimage.label(m_ara, structure=ESTRUCT8)
    if n == 0:
        return lab, 0
    mida = ndimage.sum(m_ara, lab, range(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = mida >= min_px
    lab = np.where(keep[lab], lab, 0)
    lab, n = ndimage.label(lab > 0, structure=ESTRUCT8)   # reetiqueta
    return lab, n


def detecta(cub, ok, k, llindar=6, min_px=3, solap=0.5, tol=1, max_min=240, M=None):
    """
    Avisos a l'instant k del cub (índex de fotograma). Requereix que el fotograma k existi.
    tol: píxels de tolerància espacial (cel·les que "oscil·len") i temporal (±1 fotograma).
    """
    if not ok[k]:
        return []
    if M is None:
        M = mascares(cub, ok, llindar)      # es pot passar precalculada (el mateix cub per a molts k)
    lab, n = cel_les(M[k], min_px)
    if n == 0:
        return []
    mm_h = P.taula_mm_h()
    passos = int(max_min / PAS)
    out = []
    for i in range(1, n + 1):
        cel = lab == i
        area = int(cel.sum())
        yy, xx = np.nonzero(cel)                  # la dilatació només cal al voltant de la cel·la (marge 2*tol)
        mg = 2 * tol
        by0, by1 = max(0, yy.min() - mg), min(cel.shape[0], yy.max() + 1 + mg)
        bx0, bx1 = max(0, xx.min() - mg), min(cel.shape[1], xx.max() + 1 + mg)
        cel_c = cel[by0:by1, bx0:bx1]
        # durada enganxada: es retrocedeix mentre el solapament es mantingui
        dur = 0
        buits = 0
        for j in range(1, min(passos, k) + 1):
            if not ok[k - j]:
                buits += 1                 # fotograma que falta: se salta (fins a MAX_BUITS seguits)
                if buits > MAX_BUITS:
                    break
                continue
            buits = 0
            prev = M[k - j][by0:by1, bx0:bx1] | (M[k - j - 1][by0:by1, bx0:bx1] if (k - j - 1 >= 0 and ok[k - j - 1]) else False)
            if tol:
                prev = ndimage.binary_dilation(prev, structure=ESTRUCT8, iterations=tol)
            if (cel_c & prev).sum() / area < solap:
                break
            dur = j * PAS
        # mm acumulats a la cel·la des de l'inici de l'enganxament (mitjana i màxim per píxel)
        n_acum = dur // PAS + 1
        sub = cub[k - n_acum + 1:k + 1][:, cel]
        valid = ok[k - n_acum + 1:k + 1]
        mm = (mm_h[np.minimum(np.where(sub == 255, 0, sub), 12)] * (PAS / 60.0))[valid]
        mm_pix = mm.sum(axis=0) if mm.size else np.zeros(1)
        if mm.size and len(valid) > valid.sum():       # fotogrames que falten: es reparteix la pluja segons els disponibles
            mm_pix = mm_pix * (len(valid) / valid.sum())
        ys, xs = np.nonzero(cel)
        out.append({
            "cy": float(ys.mean()), "cx": float(xs.mean()), "area_px": area,
            "enganxada_min": dur, "classe_max": int(cub[k][cel].max()),
            "mm_mitjana": float(mm_pix.mean()), "mm_max": float(mm_pix.max()),
            "mask": cel,
        })
    return out
