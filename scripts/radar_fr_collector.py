#!/usr/bin/env python3
"""Radar França (Météo-France, API Données Publiques Radar): lame d'eau 500 m -> PNG retallat (Catalunya + nord) en Web Mercator.
Escriu data/radar_fr/ld_AAAAMMDD_HHMM.png i data/radar_fr/meta.json; guarda només els últims NMAX fotogrames."""
import io, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, requests, h5py
from PIL import Image
from pyproj import CRS, Transformer
import radar_fr as rf

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "radar_fr"
NMAX = 24
W, E, S, N = -0.8, 4.8, 40.3, 44.3          # finestra: Catalunya + nord
PX = 700.0                                   # mida de píxel en metres de Mercator (~520 m de terra a 42 °N)
BREAKS = [0.1, 0.2, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 20, 24, 30, 40, 50, 60, 80, 100, 125]   # mm/h (= MOD_PAL_H del visor)
RGB = [(180,215,255), (117,186,255), (53,154,255), (4,130,255), (0,105,210), (0,54,127), (20,143,27), (26,207,5), (99,237,7),
       (255,244,43), (232,220,0), (240,96,0), (255,127,39), (255,166,106), (248,78,120), (247,30,84), (191,0,0), (136,0,0),
       (100,0,127), (194,0,251), (221,102,255), (235,166,255), (249,230,255), (212,212,212), (150,150,150)]
COLS = ["#%02x%02x%02x" % c for c in RGB]


def hexrgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def main():
    sess = requests.Session()
    hdr = rf.capcalera(sess)
    r = rf.get(sess, hdr, "/mosaiques/METROPOLE/observations/LAME_D_EAU")
    if r is None:
        return 1
    vt = next((l.get("validity_time") for l in r.json()["links"] if "maille=500" in l.get("href", "")), None)
    if not vt:
        print("No trobo el producte de 500 m"); return 1
    t = datetime.strptime(vt, "%Y-%m-%dT%H:%M:%SZ")
    nom = f"ld_{t:%Y%m%d_%H%M}.png"
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / nom).exists():
        print("Radar FR: ja tinc", nom); return 0
    r = rf.get(sess, hdr, "/mosaiques/METROPOLE/observations/LAME_D_EAU/produit", {"maille": "500"})
    if r is None:
        return 1
    h = h5py.File(io.BytesIO(r.content), "r")
    raw = h["dataset1/data1/data"][:]
    wt = h["dataset1/data1/what"].attrs
    gain, off, nodata, undet = float(wt["gain"]), float(wt["offset"]), float(wt["nodata"]), float(wt["undetect"])
    wh = h["where"].attrs
    pd = wh["projdef"].decode() if isinstance(wh["projdef"], bytes) else str(wh["projdef"])
    ny0, nx0 = raw.shape
    xsc, ysc = float(wh["xscale"]), float(wh["yscale"])
    t_rad = Transformer.from_crs("EPSG:4326", CRS.from_proj4(pd), always_xy=True)
    xul, yul = t_rad.transform(float(wh["UL_lon"]), float(wh["UL_lat"]))
    xlr, ylr = t_rad.transform(float(wh["LR_lon"]), float(wh["LR_lat"]))
    err = max(abs(xul + nx0 * xsc - xlr), abs(yul - ny0 * ysc - ylr))
    print(f"Comprovació de geometria: error a la cantonada LR = {err:.0f} m" + ("  ** REVISAR **" if err > 2000 else ""))

    t_m = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    t_inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x0, y0 = t_m.transform(W, S)
    x1, y1 = t_m.transform(E, N)
    nx, ny = int((x1 - x0) / PX), int((y1 - y0) / PX)
    xs = x0 + (np.arange(nx) + 0.5) * PX
    ys = y1 - (np.arange(ny) + 0.5) * PX
    X, Y = np.meshgrid(xs, ys)
    lon, lat = t_inv.transform(X, Y)
    rx, ry = t_rad.transform(lon, lat)
    j = np.floor((rx - xul) / xsc).astype(int)
    i = np.floor((yul - ry) / ysc).astype(int)
    ok = (i >= 0) & (i < ny0) & (j >= 0) & (j < nx0)
    v = raw[np.clip(i, 0, ny0 - 1), np.clip(j, 0, nx0 - 1)].astype(float)
    ok &= (v != nodata) & (v != undet)
    rate = np.where(ok, (v * gain + off) * 12.0, 0.0)                 # acumulat de 5 min -> mm/h
    cls = np.digitize(rate, BREAKS).astype(np.uint8)                  # 0 = transparent
    pal = [0, 0, 0] + [c for h_ in COLS for c in hexrgb(h_)]
    pal += [0] * (768 - len(pal))
    im = Image.fromarray(cls, "P"); im.putpalette(pal)
    im.save(DEST / nom, transparency=0, optimize=True)

    yb0, yb1 = y1 - ny * PX, y1
    xb1 = x0 + nx * PX
    la0 = t_inv.transform(x0, yb0)[1]; lo0 = t_inv.transform(x0, yb0)[0]
    la1 = t_inv.transform(xb1, yb1)[1]; lo1 = t_inv.transform(xb1, yb1)[0]
    fr = sorted(p.name for p in DEST.glob("ld_*.png"))
    for vell in fr[:-NMAX]:
        (DEST / vell).unlink()
    fr = fr[-NMAX:]
    meta = {"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "font": "Météo-France (Llicència Oberta 2.0)",
            "unitat": "mm/h", "bounds": [[la0, lo0], [la1, lo1]], "limits": BREAKS, "colors": COLS,
            "frames": [{"t": datetime.strptime(f[3:16], "%Y%m%d_%H%M").strftime("%Y-%m-%dT%H:%MZ"), "f": f} for f in fr]}
    (DEST / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    print(f"Radar FR: {nom} {nx}x{ny} px, {(DEST / nom).stat().st_size / 1024:.0f} kB, plou (>=0.1 mm/h) al {100 * (cls > 0).mean():.1f}% del retall, màx {rate.max():.1f} mm/h, {len(fr)} fotogrames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
