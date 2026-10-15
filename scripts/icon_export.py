#!/usr/bin/env python3
"""ICON-EU (DWD) per al visor: llegeix ICONEU_surface_AAAAMMDD_HH.nc (precipitació total acumulada) i escriu data/models/icon/{precip_h.png,meta.json}
amb el mateix format que WRF i AROME (vegeu models_export.py). Es crida des de models_export.py; també es pot executar sol.
- Variable de pluja: la primera que existeixi de TOT_PREC, tot_prec, tp, APCP (kg/m2 = mm acumulats des de l'inici del run).
- Només s'exporta el tram horari contigu des de l'inici (ICON-EU passa a 3 h més enllà de +78 h).
- Malla regular (lat/lon 1D) o no estructurada/2D (lat/lon o clat/clon, en graus o radians).
No genera cap figura."""
import argparse, glob, json, os, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from models_export import graella_destinacio, escriu_sprite, escriu_atomic, COLS, ESCALA, NODATA

RE_F = re.compile(r"ICONEU_surface_(\d{8})_(\d{2})\.nc$")
VARS_PLUJA = ("TOT_PREC", "tot_prec", "tp", "APCP")


def troba_ultim(carpeta, min_edat_s=120):
    cand = []
    for f in glob.glob(os.path.join(carpeta, "ICONEU_surface_*_*.nc")):
        m = RE_F.search(os.path.basename(f))
        if m and time.time() - os.path.getmtime(f) > min_edat_s:      # que no s'estigui escrivint
            cand.append((m.group(1) + m.group(2), f))
    if not cand:
        return None, None
    cod, f = sorted(cand)[-1]
    return datetime.strptime(cod, "%Y%m%d%H").replace(tzinfo=timezone.utc), f


def _cerca(d, noms):
    for n in noms:
        if n in d.variables:
            return d.variables[n]
    return None


def _graus(a, v):
    a = np.array(a, dtype=np.float64)
    un = (getattr(v, "units", "") or "").lower()
    return np.degrees(a) if ("rad" in un or np.nanmax(np.abs(a)) <= 6.3) and "deg" not in un else a


def _hores(tv, run):
    """Hores de previsió des de l'inici del run; accepta 'nanoseconds/seconds/hours... since AAAA-MM-DD HH:MM:SS'."""
    m = re.match(r"\s*(\w+)\s+since\s+(.+)", getattr(tv, "units", "") or "")
    fac = {"nanoseconds": 1e-9, "microseconds": 1e-6, "milliseconds": 1e-3, "seconds": 1.0, "minutes": 60.0, "hours": 3600.0, "days": 86400.0}
    if not m or m.group(1).lower() not in fac:
        return None
    try:
        t0 = datetime.fromisoformat(m.group(2).strip().replace("Z", "").replace(" UTC", "")[:19].replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    v = np.array(np.ma.filled(tv[:], np.nan), dtype=np.float64)
    return (t0 - run).total_seconds() / 3600 + v * fac[m.group(1).lower()] / 3600


def exporta_icon(carpeta, sortida, forca, res_deg, bbox):
    import netCDF4 as nc
    run, fitxer = troba_ultim(carpeta)
    if run is None:
        print("ICON-EU: cap fitxer ICONEU_surface_* a", carpeta)
        return None
    run_txt = run.strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = Path(sortida) / "icon"; meta_p = dest / "meta.json"
    if not forca and meta_p.exists():
        try:
            m = json.loads(meta_p.read_text())
            if m.get("run_utc") == run_txt and m.get("font_mtime") == int(os.path.getmtime(fitxer)):
                print(f"ICON-EU: run {run_txt} ja exportat ({m.get('passos')} passos)")
                return m
        except Exception:
            pass
    d = nc.Dataset(fitxer)
    v = _cerca(d, VARS_PLUJA)
    if v is None:
        print("ICON-EU: no trobo la pluja acumulada; variables:", sorted(d.variables)); d.close(); return None
    # --- temps -> hores de previsió
    tv = _cerca(d, ("time", "valid_time", "t"))
    n_t = v.shape[0] if v.ndim >= 3 else 1
    if tv is not None and len(tv) == n_t and n_t > 1:
        h = _hores(tv, run)
        if h is None:
            print("ICON-EU: unitats de temps no reconegudes (", getattr(tv, "units", None), "): suposo passos d'1 h"); h = np.arange(n_t, dtype=float)
    else:
        h = np.arange(n_t, dtype=float)
    ordre = np.argsort(h); h = h[ordre]
    # tram horari contigu 0,1,2,... (la pluja a +0 h pot no existir: es posa a 0)
    idx = []; k = 0
    for hh in h:
        if abs(hh - k) < 1e-3:
            idx.append(int(np.where(h == hh)[0][0])); k += 1
        elif hh > k:
            break
    if len(idx) < 2:
        print("ICON-EU: menys de 2 passos horaris; hores:", h[:10]); d.close(); return None
    # --- coordenades
    la = _cerca(d, ("lat", "latitude", "clat")); lo = _cerca(d, ("lon", "longitude", "clon"))
    lat = _graus(la[:], la); lon = _graus(lo[:], lo)
    s, w, n, e = bbox
    xs, lats, W, H = graella_destinacio(s, w, n, e, res_deg)
    XX, YY = np.meshgrid(xs, lats)
    data = np.ma.filled(np.ma.asarray(v[:]), np.nan).astype(np.float64)
    if data.ndim == 4:
        data = data[:, 0]
    data = data[ordre][idx]
    d.close()
    acum = [np.clip(a, 0, None) for a in data]
    hor = [np.zeros_like(acum[0])] + [np.clip(acum[i] - acum[i - 1], 0, None) for i in range(1, len(acum))]
    if lat.ndim == 1 and lon.ndim == 1 and data.ndim == 3 and data.shape[1:] == (lat.size, lon.size):
        from scipy.ndimage import map_coordinates
        # índexs fraccionaris (la malla pot venir amb la latitud creixent o decreixent)
        fy = np.interp(YY, lat, np.arange(lat.size)) if lat[0] < lat[-1] else np.interp(YY, lat[::-1], np.arange(lat.size)[::-1])
        fx = np.interp(XX, lon, np.arange(lon.size))
        fora = (YY < lat.min()) | (YY > lat.max()) | (XX < lon.min()) | (XX > lon.max())
        camps = []
        for hh_ in hor:
            r = map_coordinates(hh_, [fy, fx], order=1, mode="nearest"); r[fora] = np.nan; camps.append(r)
    else:
        from scipy.interpolate import LinearNDInterpolator
        if lat.ndim == 1 and lon.ndim == 1 and lat.size != lon.size:
            lon, lat = np.meshgrid(lon, lat)
        lat, lon = lat.ravel(), lon.ravel()
        m = (lat > s - 1) & (lat < n + 1) & (lon > w - 1) & (lon < e + 1)
        pts = np.column_stack([lon[m], lat[m]])
        val = np.column_stack([h_.reshape(-1)[m] for h_ in hor])
        R = LinearNDInterpolator(pts, val)(np.column_stack([XX.ravel(), YY.ravel()]))
        camps = [R[:, i].reshape(H, W) for i in range(R.shape[1])]
    dest.mkdir(parents=True, exist_ok=True)
    escriu_sprite(camps, dest / "precip_h.png")
    meta = {"model": "icon", "nom": "ICON-EU", "run_utc": run_txt, "pas_h": 1, "passos": len(camps),
            "bounds": [[round(s, 4), round(w, 4)], [round(n, 4), round(e, 4)]], "w": W, "h": H, "cols": COLS,
            "escala": ESCALA, "nodata": NODATA, "fitxer": "precip_h.png", "resolucio_km": 6.5, "font_mtime": int(os.path.getmtime(fitxer))}
    escriu_atomic(meta_p, json.dumps(meta, separators=(",", ":")))
    print(f"ICON-EU: OK run {run_txt} {W}x{H} px, {len(camps)} passos, màxim horari {np.nanmax(np.stack(camps)):.1f} mm/h")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--icon-dir", default="/home/labfire/data/ICON-EU"); ap.add_argument("--sortida", default="data/models")
    ap.add_argument("--res", type=float, default=0.04); ap.add_argument("--bbox", type=float, nargs=4, default=[38.8, -2.2, 44.0, 5.0])
    ap.add_argument("--forca", action="store_true")
    a = ap.parse_args(); exporta_icon(a.icon_dir, a.sortida, a.forca, a.res, a.bbox)
