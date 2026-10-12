#!/usr/bin/env python3
"""Reflectivitat radar de Météo-France (mosaic nacional 1 km, BUFR IMFR27) -> PNG transparent per al visor.
Retalla Catalunya + nord (la mateixa finestra que la lame d'eau), usa la paleta de reflectivitat d'AEMET (15-65 dBZ).
Surt: data/radar_fr/rf_AAAAMMDD_HHMM.png + data/radar_fr/refl_meta.json
Ús:  python3 scripts/radar_fr_refl_collector.py            (baixa l'última mosaic)
     python3 scripts/radar_fr_refl_collector.py --local fitxer.bin   (prova sense xarxa)"""
import json, os, sys, time, datetime as dt
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bufr_refl

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "radar_fr"
NMAX = 36                                   # ~3 h de fotogrames de 5 min
W, E, S, N = -0.8, 4.8, 40.3, 44.3          # finestra (idèntica a la lame d'eau)
PX = 700.0                                  # metres per píxel (Mercator)
LIMITS = [15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
COLORS = [(150, 215, 255), (70, 160, 255), (0, 190, 220), (0, 190, 80), (170, 215, 0), (255, 235, 0),
          (255, 150, 0), (240, 40, 20), (170, 0, 30), (210, 0, 170), (150, 60, 220)]
ALT_LIM = [0, 1000, 2000, 3000, 4000, 5000, 6000, 8000]      # m: alçada de la mesura (límits inferiors)
ALT_COL = [(68, 1, 84), (65, 68, 135), (42, 120, 142), (34, 168, 132), (122, 209, 81), (253, 231, 37), (255, 150, 0), (240, 40, 20)]
ALFA = 200                                  # opacitat dels píxels (0-255); el visor hi afegeix la seva
PROJ = "+proj=stere +lat_0=90 +lon_0=0 +lat_ts=45 +ellps=WGS84 +datum=WGS84"
UL_LON, UL_LAT, DX = -9.965, 53.67, 1000.0  # cantonada superior esquerra de la mosaic, 1 km


def baixa():
    import requests
    import radar_fr as rf
    s = requests.Session()
    h = rf.capcalera(s)
    if not isinstance(h, dict):
        h = dict(h)
    ruta = "/mosaiques/METROPOLE/observations/REFLECTIVITE/produit?maille=1000"
    ultim = None
    for base in ("https://public-api.meteofrance.fr/public/DPRadar/v1", "https://public-api.meteofrance.fr/public/DPRadar"):
        r = s.get(base + ruta, headers=h, timeout=90)
        if r.status_code == 200:
            return r.content
        ultim = r
    raise RuntimeError(f"HTTP {ultim.status_code}: {ultim.text[:200]}")


def finestra():
    """Retorna (índexs i,j de la mosaic per a cada píxel de sortida, forma)."""
    m = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = m.transform(W, S)
    x1, y1 = m.transform(E, N)
    nx, ny = int((x1 - x0) / PX), int((y1 - y0) / PX)
    xs = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
    ys = y1 - (np.arange(ny) + 0.5) * (y1 - y0) / ny
    X, Y = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(X, Y)
    st = Transformer.from_crs("EPSG:4326", PROJ, always_xy=True)
    xu, yu = st.transform(UL_LON, UL_LAT)
    px, py = st.transform(lon, lat)
    j = np.floor((px - xu) / DX).astype(int)
    i = np.floor((yu - py) / DX).astype(int)
    return i, j, (ny, nx)


def pinta(z, i, j, forma):
    ok = (i >= 0) & (i < 1536) & (j >= 0) & (j < 1536)
    v = np.full(forma, np.nan, np.float32)
    v[ok] = z[i[ok], j[ok]]
    cl = np.digitize(v, LIMITS) - 1             # -1 = <15 dBZ o sense dada
    rgba = np.zeros(forma + (4,), np.uint8)
    for k, c in enumerate(COLORS):
        m = cl == k if k < len(COLORS) - 1 else cl >= k
        rgba[m] = (*c, ALFA)
    rgba[~np.isfinite(v)] = 0
    return Image.fromarray(rgba, "RGBA"), v


def pinta_alcada(h, i, j, forma):
    ok = (i >= 0) & (i < 1536) & (j >= 0) & (j < 1536)
    v = np.full(forma, np.nan, np.float32)
    v[ok] = h[i[ok], j[ok]]
    cl = np.clip(np.digitize(v, ALT_LIM) - 1, 0, len(ALT_COL) - 1)
    rgba = np.zeros(forma + (4,), np.uint8)
    for k, c in enumerate(ALT_COL):
        rgba[cl == k] = (*c, ALFA)
    rgba[~np.isfinite(v)] = 0
    return Image.fromarray(rgba, "RGBA")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 2 and sys.argv[1] == "--local":
        brut = open(sys.argv[2], "rb").read()
    else:
        brut = baixa()
    t0 = time.time()
    z, h = bufr_refl.reflectivitat(brut)
    nom = f"rf_{h:%Y%m%d_%H%M}.png"
    meta_f = OUT / "refl_meta.json"
    meta = {"frames": []}
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text())
        except Exception:
            pass
    if any(f["f"] == nom for f in meta["frames"]) and (OUT / nom).exists():
        print(f"radar fr refl: {nom} ja existeix")
        return
    i, j, forma = finestra()
    im, v = pinta(z, i, j, forma)
    im.save(OUT / nom, optimize=True)
    pinta_alcada(bufr_refl.alcada(brut), i, j, forma).save(OUT / nom.replace("rf_", "rh_"), optimize=True)
    fr = [f for f in meta["frames"] if f["f"] != nom] + [{"t": h.strftime("%Y-%m-%dT%H:%MZ"), "f": nom}]
    fr.sort(key=lambda f: f["t"])
    for f in fr[:-NMAX]:
        try:
            (OUT / f["f"]).unlink()
            (OUT / f["f"].replace("rf_", "rh_")).unlink()
        except FileNotFoundError:
            pass
    fr = fr[-NMAX:]
    meta.update({"bounds": [[S, W], [N, E]], "limits": LIMITS, "alcada_limits": ALT_LIM,
                 "alcada_colors": ["rgb(%d,%d,%d)" % c for c in ALT_COL],
                 "colors": ["rgb(%d,%d,%d)" % c for c in COLORS], "frames": fr,
                 "font": "Météo-France (mosaic radar 1 km)", "actualitzat": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")})
    meta_f.write_text(json.dumps(meta, separators=(",", ":")))
    print(f"radar fr refl: {nom} {forma[1]}x{forma[0]} px, {(OUT/nom).stat().st_size/1024:.0f} kB, màx {np.nanmax(v):.1f} dBZ, {time.time()-t0:.1f} s")


if __name__ == "__main__":
    main()
