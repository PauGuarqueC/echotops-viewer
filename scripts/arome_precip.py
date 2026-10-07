#!/usr/bin/env python3
"""Descarrega la precipitació total acumulada d'AROME (Météo-France, WCS 0,025°) de l'última passada
i la desa en un .npz que després llegeix models_export.py.

És lleuger: ~49 peticions (H+0..H+48), 1-2 minuts. Es salta si la passada ja està baixada.

Autenticació (portail-api.meteofrance.fr, subscripció a l'API AROME). Mai es mostra ni es desa al repositori:
  - OAuth2 (recomanat, no caduca): fitxer ~/.arome_oauth (chmod 600) amb "consumer_key:consumer_secret" en una línia
    (o variables METEOFRANCE_CLIENT_ID i METEOFRANCE_CLIENT_SECRET). El script demana ell mateix un token cada execució.
  - Clau d'API: variable METEOFRANCE_API_KEY o fitxer ~/.arome_key (caduca segons la durada triada al portal).

Ús:
  python3 arome_precip.py --sortida ~/arome_precip
Opcions útils: --run 2026-10-07T00 (força una passada), --forca, --auth bearer (si la clau és un token OAuth).
Requisits: numpy, requests, eccodes."""
import argparse
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests

BASE = os.environ.get("AROME_BASE", "https://public-api.meteofrance.fr/public/arome/1.0/wcs/MF-NWP-HIGHRES-AROME-0025-FRANCE-WCS")
COV = "TOTAL_PRECIPITATION__GROUND_OR_WATER_SURFACE___"
PERIODE = "_PT1H"                            # cobertura de pluja acumulada en 1 h (el temps demanat és el final del període)
RE_COV = re.compile(re.escape(COV) + r"(\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2}Z)" + PERIODE)
N, W, S, E = 45.0, -3.0, 38.0, 6.0          # mateix domini que el descarregador del CTFC (cobreix Catalunya amb marge)
MAX_H = 48
PAUSA = float(os.environ.get("AROME_PAUSA", "1.3"))                                  # s entre peticions (el pla gratuït limita a ~50 peticions/min)


def carrega_clau():
    k = os.environ.get("METEOFRANCE_API_KEY", "").strip()
    if not k:
        p = Path.home() / ".arome_key"
        if p.exists():
            k = p.read_text().strip()
    return k


TOKEN_URL = os.environ.get("AROME_TOKEN_URL", "https://portail-api.meteofrance.fr/token")


def credencials_oauth():
    i, sct = os.environ.get("METEOFRANCE_CLIENT_ID", "").strip(), os.environ.get("METEOFRANCE_CLIENT_SECRET", "").strip()
    if i and sct:
        return i, sct
    p = Path.home() / ".arome_oauth"
    if p.exists():
        t = ":".join(x.strip() for x in p.read_text().strip().splitlines()[:2])        # "clau:secret" en una línia o en dues
        if ":" not in t:                                                                # o el text base64 que dona el portal després de "Basic"
            try:
                import base64
                t = base64.b64decode(t.replace("Basic", "").strip()).decode()
            except Exception:
                pass
        if ":" in t:
            i, sct = t.split(":", 1)
            return i.strip(), sct.strip()
    return None


def token_oauth(sess, cred):
    r = sess.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=cred, timeout=30)
    if r.status_code != 200:
        sys.exit(f"No s'ha pogut obtenir el token OAuth2 (HTTP {r.status_code}). Revisa consumer key/secret i la subscripció a l'API AROME.")
    return r.json()["access_token"]


def capcaleres(clau, mode):
    return {"apikey": clau} if mode == "apikey" else {"Authorization": f"Bearer {clau}"}


def get(sess, url, params, hdr, intents=6, timeout=60):
    """GET amb reintents (429 i 5xx amb espera creixent). Retorna la resposta o None si 404."""
    for i in range(intents):
        try:
            r = sess.get(url, params=params, headers=hdr, timeout=timeout)
        except requests.RequestException as ex:
            print(f"  xarxa: {type(ex).__name__}; reintent {i + 1}/{intents}", file=sys.stderr)
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            sys.exit(f"Clau rebutjada per Météo-France (HTTP {r.status_code}). Revisa la subscripció a l'API AROME i el mode --auth.")
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (i + 1))
            continue
        print(f"  HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return None
    return None


def passades_disponibles(sess, hdr):
    """Passades que tenen la cobertura de precipitació total, de la més recent a la més antiga."""
    r = get(sess, BASE + "/GetCapabilities", {"service": "WCS", "version": "2.0.1", "language": "eng"}, hdr, timeout=120)
    if r is not None:
        runs = sorted(set(RE_COV.findall(r.text)), reverse=True)
        if runs:
            return runs
    # Alternativa si no es pot llegir el catàleg: passades cada 3 h cap enrere
    ara = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    ara -= timedelta(hours=ara.hour % 3)
    return [(ara - timedelta(hours=3 * i)).strftime("%Y-%m-%dT%H.00.00Z") for i in range(0, 10)]


def run_a_dt(txt):
    return datetime.strptime(txt, "%Y-%m-%dT%H.%M.%SZ").replace(tzinfo=timezone.utc)


def decodifica(grib_bytes):
    """Un missatge GRIB → (matriu nord→sud, lat1, lon1, dlat, dlon)."""
    import eccodes as ec
    fd, tmp = tempfile.mkstemp(suffix=".grib2")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(grib_bytes)
        with open(tmp, "rb") as fh:
            h = ec.codes_grib_new_from_file(fh)
            if h is None:
                return None
            ni, nj = ec.codes_get(h, "Ni"), ec.codes_get(h, "Nj")
            v = np.array(ec.codes_get_values(h), dtype=np.float64).reshape(nj, ni)
            la1 = ec.codes_get(h, "latitudeOfFirstGridPointInDegrees")
            lo1 = ec.codes_get(h, "longitudeOfFirstGridPointInDegrees")
            la2 = ec.codes_get(h, "latitudeOfLastGridPointInDegrees")
            dlat = abs(ec.codes_get(h, "jDirectionIncrementInDegrees"))
            dlon = ec.codes_get(h, "iDirectionIncrementInDegrees")
            if ec.codes_get(h, "jScansPositively"):                       # sud→nord: es gira perquè la primera fila sigui el nord
                v = v[::-1]
                la1 = la2
            if lo1 > 180:
                lo1 -= 360
            ec.codes_release(h)
            return v, la1, lo1, dlat, dlon
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sortida", default=str(Path.home() / "arome_precip"))
    ap.add_argument("--run", help="passada concreta, p. ex. 2026-10-07T00 (per defecte, la més recent disponible)")
    ap.add_argument("--forca", action="store_true", help="torna a baixar encara que ja hi sigui")
    ap.add_argument("--auth", choices=["oauth2", "apikey", "bearer"], default=None, help="per defecte: oauth2 si hi ha ~/.arome_oauth, si no apikey")
    ap.add_argument("--min-edat", type=float, default=2.0, help="hores mínimes entre consultes al catàleg (per defecte 2)")
    ap.add_argument("--max-h", type=int, default=MAX_H)
    a = ap.parse_args()

    sess = requests.Session()
    cred = credencials_oauth()
    mode = a.auth or ("oauth2" if cred else "apikey")
    if mode == "oauth2":
        if not cred:
            sys.exit("Falten les credencials OAuth2: posa 'consumer_key:consumer_secret' a ~/.arome_oauth")
        clau = token_oauth(sess, cred)
        mode = "bearer"
    else:
        clau = carrega_clau()
        if not clau:
            sys.exit("Falta la clau: posa-la a METEOFRANCE_API_KEY o a ~/.arome_key (o fes servir OAuth2 amb ~/.arome_oauth)")
    hdr = capcaleres(clau, mode)
    sortida = Path(a.sortida).expanduser()
    sortida.mkdir(parents=True, exist_ok=True)

    if not a.forca and not a.run:                                          # evita consultar el catàleg a cada execució del cron
        ult = sorted(sortida.glob("arome_tp_*.npz"))
        if ult and time.time() - ult[-1].stat().st_mtime < a.min_edat * 3600:
            print(f"AROME: {ult[-1].name} és recent (< {a.min_edat} h); no es torna a consultar")
            return 0
    if a.run:
        runs = [datetime.strptime(a.run, "%Y-%m-%dT%H").strftime("%Y-%m-%dT%H.00.00Z")]
    else:
        runs = passades_disponibles(sess, hdr)

    for run_txt in runs[:6]:
        run = run_a_dt(run_txt)
        nom = sortida / f"arome_tp_{run:%Y%m%d_%H}.npz"
        if nom.exists() and not a.forca:
            try:
                completa = len(np.load(nom)["passos"]) >= 40
            except Exception:
                completa = False
            if completa:
                print(f"AROME: passada {run:%Y-%m-%d %H} UTC ja baixada ({nom.name})")
                return 0
        horari, geo = {}, None
        cov = COV + run_txt + PERIODE
        print(f"AROME: baixant passada {run:%Y-%m-%d %H} UTC …")
        for h in range(1, a.max_h + 1):                                    # H+0 no existeix a la cobertura d'1 h
            t = (run + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
            params = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("format", "application/wmo-grib"),
                      ("coverageId", cov), ("subset", f"time({t})"), ("subset", f"lat({S:g},{N:g})"), ("subset", f"long({W:g},{E:g})")]
            r = get(sess, BASE + "/GetCoverage", params, hdr)
            time.sleep(PAUSA)
            if r is None or not r.content.startswith(b"GRIB"):
                break                                                      # fi de l'horitzó (o passada encara incompleta)
            d = decodifica(r.content)
            if d is None:
                break
            if geo is None:
                geo = d[1:]
            horari[h] = np.clip(d[0], 0, None)
        if len(horari) < 24:                                               # passada encara en publicació o buida: provem l'anterior
            print(f"AROME: passada {run:%Y-%m-%d %H} UTC incompleta ({len(horari)} h); provo l'anterior")
            continue
        acum, tot = {}, 0
        for h in sorted(horari):                                           # acumulat des de l'inici (models_export en torna a treure les hores)
            tot = tot + horari[h]
            acum[h] = tot
        passos = sorted(acum)
        ni, nj = acum[passos[0]].shape[1], acum[passos[0]].shape[0]
        la1, lo1, dlat, dlon = geo
        tmp = nom.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, passos=np.array(passos), acum=np.stack([acum[p] for p in passos]).astype(np.float32),
                            lat1=la1, lon1=lo1, dlat=dlat, dlon=dlon, ni=ni, nj=nj, run=run_txt)
        os.replace(tmp, nom)
        for vell in sorted(sortida.glob("arome_tp_*.npz"))[:-4]:           # només es guarden les 4 darreres passades
            vell.unlink()
        print(f"AROME: OK {len(passos)} hores, graella {ni}x{nj} → {nom}")
        return 0
    print("AROME: cap passada disponible")
    return 1


if __name__ == "__main__":
    sys.exit(main())
