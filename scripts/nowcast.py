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


def detecta(cub, ok, k, llindar=6, min_px=3, solap=0.5, tol=1, max_min=240):
    """
    Avisos a l'instant k del cub (índex de fotograma). Requereix que el fotograma k existi.
    tol: píxels de tolerància espacial (cel·les que "oscil·len") i temporal (±1 fotograma).
    """
    if not ok[k]:
        return []
    M = mascares(cub, ok, llindar)
    lab, n = cel_les(M[k], min_px)
    if n == 0:
        return []
    mm_h = P.taula_mm_h()
    passos = int(max_min / PAS)
    out = []
    for i in range(1, n + 1):
        cel = lab == i
        area = int(cel.sum())
        # durada enganxada: es retrocedeix mentre el solapament es mantingui
        dur = 0
        for j in range(1, min(passos, k) + 1):
            if not ok[k - j]:
                break
            prev = M[k - j] | (M[k - j - 1] if (k - j - 1 >= 0 and ok[k - j - 1]) else False)
            if tol:
                prev = ndimage.binary_dilation(prev, structure=ESTRUCT8, iterations=tol)
            if (cel & prev).sum() / area < solap:
                break
            dur = j * PAS
        # mm acumulats a la cel·la des de l'inici de l'enganxament (mitjana i màxim per píxel)
        n_acum = dur // PAS + 1
        sub = cub[k - n_acum + 1:k + 1][:, cel]
        valid = ok[k - n_acum + 1:k + 1]
        mm = (mm_h[np.minimum(np.where(sub == 255, 0, sub), 12)] * (PAS / 60.0))[valid]
        mm_pix = mm.sum(axis=0) if mm.size else np.zeros(1)
        ys, xs = np.nonzero(cel)
        out.append({
            "cy": float(ys.mean()), "cx": float(xs.mean()), "area_px": area,
            "enganxada_min": dur, "classe_max": int(cub[k][cel].max()),
            "mm_mitjana": float(mm_pix.mean()), "mm_max": float(mm_pix.max()),
            "mask": cel,
        })
    return out
