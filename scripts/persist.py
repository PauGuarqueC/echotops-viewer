#!/usr/bin/env python3
"""
Persistència de precipitació intensa a partir del compost de radar AEMET (opció A:
graella amb comptadors per píxel).

Entrada : directori amb data/composit/AAAAMMDD/radar_AAAAMMDDHHMMSS.npz  (classes 0-12)
Sortida : per a cada finestra (hores) -> NPZ amb els camps per píxel + PNG de visualització
          + resum JSON amb els píxels/zones més persistents.

Camps per píxel, en una finestra que acaba a l'últim fotograma:
  minuts_sobre   minuts amb classe >= llindar
  ratxa_max      ratxa contínua més llarga (minuts) per sobre del llindar
  episodis       nombre d'episodis separats (entrades al llindar)  -> "training"
  acum_mm        precipitació estimada (mm) amb Z-R sobre el valor central de la classe
  cobertura      fracció de fotogrames de la finestra realment disponibles (0-1)
"""
import argparse, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

PAS_MIN = 10  # cadència del compost

# Valor central (dBZ) de cada classe de l'escala AEMET (1 = 5-15 dBZ ... 12 = >65 dBZ)
DBZ_CLASSE = {1: 10.0, 2: 17.5, 3: 22.5, 4: 27.5, 5: 32.5, 6: 37.5, 7: 42.5,
              8: 47.5, 9: 52.5, 10: 57.5, 11: 62.5, 12: 67.5}
DBZ_TOPALL = 55.0   # topall per evitar sobreestimar per calamarsa
CLASSE_MIN_PLUJA = 2  # per sota (<15 dBZ) no es compta com a pluja
FRE = re.compile(r"radar_(\d{8})(\d{6})\.npz$")


def taula_mm_h():
    """Taula classe -> mm/h (Marshall-Palmer Z = 200 R^1.6) amb topall de dBZ."""
    t = np.zeros(13, np.float32)
    for c, dbz in DBZ_CLASSE.items():
        if c >= CLASSE_MIN_PLUJA:
            z = 10 ** (min(dbz, DBZ_TOPALL) / 10.0)
            t[c] = (z / 200.0) ** (1 / 1.6)
    return t


def llista_fotogrames(arrel: Path):
    out = {}
    for p in sorted(arrel.glob("composit/*/radar_*.npz")):
        m = FRE.search(p.name)
        if m:
            ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            out[ts] = p
    return out


def carrega_finestra(frames, fi, hores):
    """Apila els fotogrames de [fi-hores, fi] a pas fix; els que falten queden com a NaN (255)."""
    ini = fi - timedelta(hours=hores)
    n = int(hores * 60 / PAS_MIN) + 1
    timestamps = [ini + timedelta(minutes=PAS_MIN * k) for k in range(n)]
    shape = None
    for p in frames.values():
        shape = np.load(p)["data"].shape
        break
    cub = np.full((n, *shape), 255, np.uint8)   # 255 = fotograma absent
    ok = np.zeros(n, bool)
    for k, ts in enumerate(timestamps):
        p = frames.get(ts)
        if p is not None:
            cub[k] = np.load(p)["data"]
            ok[k] = True
    return timestamps, cub, ok


def mascara_clutter(frames, llindar, mostra=300, fraccio=0.5):
    """Píxels que superen el llindar en > fraccio dels fotogrames de la mostra = ecos fixes."""
    ts = sorted(frames)
    pas = max(1, len(ts) // mostra)
    sel = ts[::pas]
    acc, n = None, 0
    for t in sel:
        a = np.load(frames[t])["data"] >= llindar
        acc = a.astype(np.uint16) if acc is None else acc + a
        n += 1
    return (acc / n) > fraccio


def calcula(cub, ok, llindar):
    n, h, w = cub.shape
    mm_h = taula_mm_h()
    minuts = np.zeros((h, w), np.uint16)
    run = np.zeros((h, w), np.uint16)
    run_max = np.zeros((h, w), np.uint16)
    epis = np.zeros((h, w), np.uint8)
    acum = np.zeros((h, w), np.float32)
    prev = np.zeros((h, w), bool)
    for k in range(n):
        if not ok[k]:
            run[:] = 0           # un forat trenca la ratxa (no sabem què va passar)
            prev[:] = False
            continue
        cl = cub[k]
        sobre = cl >= llindar
        minuts += sobre
        nou = sobre & ~prev
        epis += nou
        run = np.where(sobre, run + 1, 0).astype(np.uint16)
        np.maximum(run_max, run, out=run_max)
        acum += mm_h[np.minimum(cl, 12)] * (PAS_MIN / 60.0)
        prev = sobre
    return {
        "minuts_sobre": minuts * PAS_MIN,
        "ratxa_max": run_max * PAS_MIN,
        "episodis": epis,
        "acum_mm": acum,
        "cobertura": np.float32(ok.mean()),
    }


def png_camp(camp, vmax, path, mascara=None):
    """PNG RGBA (transparent a 0) amb rampa seqüencial, sense matplotlib."""
    rampa = np.array([[255, 255, 204], [255, 237, 160], [254, 217, 118], [254, 178, 76],
                      [253, 141, 60], [252, 78, 42], [227, 26, 28], [177, 0, 38], [90, 0, 40]], np.float32)
    x = np.clip(camp.astype(np.float32) / vmax, 0, 1) * (len(rampa) - 1)
    i = np.minimum(x.astype(int), len(rampa) - 2)
    f = (x - i)[..., None]
    rgb = rampa[i] * (1 - f) + rampa[i + 1] * f
    a = np.where(camp > 0, 210, 0).astype(np.uint8)
    if mascara is not None:
        a[mascara] = 0
    img = np.dstack([rgb.astype(np.uint8), a])
    Image.fromarray(img, "RGBA").save(path)


def resum(res, bounds, mascara, top=15):
    h, w = res["ratxa_max"].shape
    lon0, lat0, lon1, lat1 = bounds["lon_min"], bounds["lat_min"], bounds["lon_max"], bounds["lat_max"]
    r = np.where(mascara, 0, res["ratxa_max"])
    idx = np.argsort(r.ravel())[::-1][:top]
    pts = []
    for i in idx:
        y, x = divmod(int(i), w)
        if r[y, x] == 0:
            break
        pts.append({
            "lat": round(lat1 - (y + 0.5) * (lat1 - lat0) / h, 3),
            "lon": round(lon0 + (x + 0.5) * (lon1 - lon0) / w, 3),
            "ratxa_min": int(res["ratxa_max"][y, x]),
            "minuts_sobre": int(res["minuts_sobre"][y, x]),
            "episodis": int(res["episodis"][y, x]),
            "acum_mm": round(float(res["acum_mm"][y, x]), 1),
        })
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arrel", default="/home/claude/javimiroo/radar-arxiu/data")
    ap.add_argument("--sortida", default="/home/claude/persistencia/sortida")
    ap.add_argument("--llindar", type=int, default=8, help="classe mínima (8 = >=45 dBZ)")
    ap.add_argument("--hores", type=float, nargs="+", default=[3, 6, 12, 24])
    ap.add_argument("--final", help="instant final UTC AAAAMMDDHHMM (per defecte, l'últim fotograma)")
    a = ap.parse_args()

    arrel = Path(a.arrel)
    frames = llista_fotogrames(arrel)
    if not frames:
        raise SystemExit("Cap fotograma trobat")
    fi = datetime.strptime(a.final, "%Y%m%d%H%M").replace(tzinfo=timezone.utc) if a.final else max(frames)
    any_json = json.loads(next(iter(arrel.glob("composit/*/radar_*.json"))).read_text())
    bounds = any_json["bounds"]
    out = Path(a.sortida); out.mkdir(parents=True, exist_ok=True)

    clutter = mascara_clutter(frames, a.llindar)
    print(f"Fotogrames: {len(frames)} | final {fi:%Y-%m-%d %H:%M}Z | llindar classe>={a.llindar} "
          f"| píxels de clutter fix: {int(clutter.sum())}")

    for hores in a.hores:
        ts, cub, ok = carrega_finestra(frames, fi, hores)
        res = calcula(cub, ok, a.llindar)
        res["minuts_sobre"] = np.where(clutter, 0, res["minuts_sobre"])
        tag = f"{int(hores)}h"
        np.savez_compressed(out / f"persist_{tag}.npz", **{k: v for k, v in res.items()})
        png_camp(res["ratxa_max"], hores * 60, out / f"ratxa_{tag}.png", clutter)
        png_camp(res["acum_mm"], 60 if hores <= 6 else 120, out / f"acum_{tag}.png", clutter)
        pts = resum(res, bounds, clutter)
        (out / f"resum_{tag}.json").write_text(json.dumps(
            {"final_utc": fi.isoformat(), "hores": hores, "llindar_classe": a.llindar,
             "cobertura": float(res["cobertura"]), "bounds": bounds, "top": pts}, indent=1))
        print(f"[{tag}] cobertura {float(res['cobertura']):.0%} | ratxa màx {int(res['ratxa_max'].max())} min "
              f"| acum màx {res['acum_mm'].max():.1f} mm | píxels amb algun episodi {int((res['episodis']>0).sum())}")
        for p in pts[:3]:
            print("    ", p)


if __name__ == "__main__":
    main()
