#!/usr/bin/env python3
"""Radar obert de Météo-France (API Données Publiques Radar). Mateixes credencials que arome_precip.py (~/.arome_oauth).
  venv/bin/python scripts/radar_fr.py estacions                         llista de radars -> ~/radar_fr/estacions.json
  venv/bin/python scripts/radar_fr.py explora                           llista zones i observacions de les mosaics
  venv/bin/python scripts/radar_fr.py mosaica ZONA OBSERVACIO [maille]  baixa el producte -> ~/radar_fr/
Context base: variable RADAR_BASE (per defecte .../public/DPRadar/v1)."""
import os, sys, json
from datetime import datetime, timezone
from pathlib import Path
import requests
import arome_precip as ap

BASE = os.environ.get("RADAR_BASE", "https://public-api.meteofrance.fr/public/DPRadar/v1")
SORTIDA = Path.home() / "radar_fr"


def capcalera(sess):
    cred = ap.credencials_oauth()
    if cred:
        return ap.capcaleres(ap.token_oauth(sess, cred), "bearer")
    k = ap.carrega_clau()
    if not k:
        sys.exit("Falten credencials: ~/.arome_oauth o ~/.arome_key")
    return ap.capcaleres(k, "apikey")


def get(sess, hdr, ruta, params=None):
    r = sess.get(BASE + ruta, headers=hdr, params=params, timeout=120)
    print(f"GET {ruta} {params or ''} -> HTTP {r.status_code}, {len(r.content)} bytes, {r.headers.get('Content-Type', '')}")
    if r.status_code != 200:
        print("  ", r.text[:300])
        return None
    return r


def mostra(r, n=1500):
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=1)[:n])
    except Exception:
        print(r.text[:n])


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("estacions", "explora", "mosaica"):
        sys.exit(__doc__)
    sess = requests.Session()
    hdr = capcalera(sess)
    SORTIDA.mkdir(exist_ok=True)
    cmd = sys.argv[1]
    if cmd == "estacions":
        r = get(sess, hdr, "/liste-stations")
        if r is not None:
            (SORTIDA / "estacions.json").write_bytes(r.content)
            mostra(r, 2500)
    elif cmd == "explora":
        r = get(sess, hdr, "/mosaiques")
        if r is None:
            return
        mostra(r)
        z = sys.argv[2] if len(sys.argv) > 2 else None
        if z:
            r2 = get(sess, hdr, f"/mosaiques/{z}")
            if r2 is not None: mostra(r2)
            r3 = get(sess, hdr, f"/mosaiques/{z}/observations")
            if r3 is not None: mostra(r3)
    else:
        if len(sys.argv) < 4:
            sys.exit("Ús: mosaica ZONA OBSERVACIO [maille]")
        z, obs = sys.argv[2], sys.argv[3]
        params = {"maille": sys.argv[4]} if len(sys.argv) > 4 else None
        r = get(sess, hdr, f"/mosaiques/{z}/observations/{obs}/produit", params)
        if r is not None:
            ext = "json" if "json" in r.headers.get("Content-Type", "") else ("png" if "png" in r.headers.get("Content-Type", "") else "bin")
            f = SORTIDA / f"mosaica_{z}_{obs}_{datetime.now(timezone.utc):%Y%m%d_%H%M}.{ext}"
            f.write_bytes(r.content)
            print("Desat:", f, "| capçaleres:", dict(r.headers))


if __name__ == "__main__":
    main()
