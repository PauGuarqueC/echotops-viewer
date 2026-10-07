#!/usr/bin/env python3
"""Col·lector de dades en temps real de l'ACA (Sentilo, accés públic): aforaments, pluviòmetres i embassaments.

Cada execució fa 3 peticions (darrera mesura de tots els sensors de cada provider) i, un cop al dia, 3 més pel catàleg.
 - Arxiu propi (fora del git):   ~/aca_arxiu/AAAA-MM.csv   (temps_utc, sensor, valor) sense duplicats
 - Per al visor (dins del repo): <sortida>/estacions.json  (catàleg compacte)  i  <sortida>/ultimes.json (darreres mesures)
L'ACA només guarda 3 mesos, de manera que l'arxiu propi és la manera de tenir-ne més.

Ús (cron cada 5-10 min):  venv/bin/python scripts/aca_collector.py --sortida data/aca
Recuperar històric:       venv/bin/python scripts/aca_collector.py --sortida data/aca --backfill 48     (hores, un cop)"""
import argparse, csv, json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

B = "https://aplicacions.aca.gencat.cat/sdim2/apirest"
TIPUS = {"aforament": "AFORAMENT-EST", "pluviometre": "PLUVIOMETREACA-EST", "embassament": "EMBASSAMENT-EST"}
S = requests.Session(); S.headers.update({"Accept": "application/json", "User-Agent": "echotops-viewer/1.0 (CTFC)"})


def get(ruta, params=None, intents=3):
    for i in range(intents):
        try:
            r = S.get(B + ruta, params=params, timeout=90)
            if r.status_code == 200 and r.text.lstrip().startswith(("{", "[")):
                return r.json()
            print(f"  ACA {ruta[:60]}: HTTP {r.status_code} {r.text[:80]!r}", file=sys.stderr)
        except (requests.RequestException, ValueError) as e:
            print(f"  ACA {ruta[:60]}: {type(e).__name__}", file=sys.stderr)
        time.sleep(3 * (i + 1))
    return None


def num(v):
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def cataleg(sortida, forca=False):
    """Catàleg compacte; es refresca un cop al dia."""
    f = sortida / "estacions.json"
    if f.exists() and not forca and time.time() - f.stat().st_mtime < 24 * 3600:
        return json.loads(f.read_text())
    est = {}
    for tipus in TIPUS:
        j = get("/catalog", {"componentType": tipus})
        if not j:
            if f.exists():
                return json.loads(f.read_text())             # millor el catàleg vell que res
            continue
        for p in j.get("providers", []):
            for s in p.get("sensors", []):
                try:
                    la, lo = (float(x) for x in s["location"].split())
                except Exception:
                    continue
                ai = s.get("componentAdditionalInfo") or {}
                e = est.setdefault(s["component"], {"id": s["component"], "tipus": tipus, "nom": (s.get("componentDesc") or "").strip(),
                                                    "lat": round(la, 5), "lon": round(lo, 5), "comarca": ai.get("Comarca"), "vars": []})
                e["vars"].append({"sensor": s["sensor"], "provider": p["provider"], "nom": (s.get("description") or "").strip(),
                                  "tipus": s.get("type"), "unitat": s.get("unit"), "mostreig_min": (s.get("additionalInfo") or {}).get("Temps mostreig (min)"),
                                  "estat": s.get("state")})
    cat = {"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "estacions": list(est.values())}
    if est:
        f.write_text(json.dumps(cat, ensure_ascii=False, separators=(",", ":")))
    return cat


def llegeix_ultimes():
    obs = {}                                                  # sensor -> [(ms, valor_text)]
    for tipus, prov in TIPUS.items():
        j = get(f"/data/{prov}")
        for s in (j or {}).get("sensors", []):
            for o in s.get("observations", []):
                if "time" in o:
                    obs.setdefault(s["sensor"], []).append((int(o["time"]), o.get("value")))
    return obs


def arxiva(obs, arx, omple=False):
    """Afegeix al CSV mensual només les mesures noves (estat a ~/aca_arxiu/.ultim.json).
    Amb omple=True (backfill) es comparen amb el contingut real dels CSV (no amb l'última mesura vista) i després s'ordenen."""
    arx.mkdir(parents=True, exist_ok=True)
    fs = arx / ".ultim.json"
    ult = json.loads(fs.read_text()) if fs.exists() else {}
    noves = 0
    obert = {}
    tocats, vistos = set(), {}
    try:
        for sensor, llista in obs.items():
            for ms, v in sorted(llista):
                if not omple and ms <= ult.get(sensor, 0):
                    continue
                t = datetime.fromtimestamp(ms / 1000, timezone.utc)
                nom = arx / f"{t:%Y-%m}.csv"
                if omple:
                    if nom not in vistos:
                        vistos[nom] = set()
                        if nom.exists():
                            with open(nom, newline="") as fh:
                                vistos[nom] = {(r[0], r[1]) for r in list(csv.reader(fh))[1:] if len(r) >= 2}
                    k = (t.strftime("%Y-%m-%dT%H:%M:%SZ"), sensor)
                    if k in vistos[nom]:
                        continue
                    vistos[nom].add(k); tocats.add(nom)
                if nom not in obert:
                    nou = not nom.exists()
                    obert[nom] = open(nom, "a", newline=""); w = csv.writer(obert[nom])
                    if nou:
                        w.writerow(["temps_utc", "sensor", "valor"])
                    obert[nom] = (obert[nom], w)
                obert[nom][1].writerow([t.strftime("%Y-%m-%dT%H:%M:%SZ"), sensor, v])
                ult[sensor] = max(ms, ult.get(sensor, 0)); noves += 1
    finally:
        for o in obert.values():
            o[0].close()
        fs.write_text(json.dumps(ult))
    for nom in tocats:                                        # backfill: deixa cada mes ordenat per temps
        with open(nom, newline="") as fh:
            rows = list(csv.reader(fh))
        cap, cos = rows[0], sorted(rows[1:], key=lambda r: (r[0], r[1]))
        with open(nom, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(cap); w.writerows(cos)
    return noves


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sortida", default="data/aca")
    ap.add_argument("--arxiu", default=str(Path.home() / "aca_arxiu"))
    ap.add_argument("--backfill", type=float, default=0, help="hores enrere per recuperar històric (una petició per sensor)")
    ap.add_argument("--forca-cataleg", action="store_true")
    a = ap.parse_args()
    sortida = Path(a.sortida); sortida.mkdir(parents=True, exist_ok=True)
    arx = Path(a.arxiu).expanduser()

    cat = cataleg(sortida, a.forca_cataleg)
    if not cat.get("estacions"):
        print("ACA: sense catàleg (API no disponible?)"); return 1

    if a.backfill:
        ara = datetime.now(timezone.utc); ini = ara - timedelta(hours=a.backfill)
        fmt = "%d/%m/%YT%H:%M:%S"
        obs, n = {}, 0
        for e in cat["estacions"]:
            for v in e["vars"]:
                j = get(f"/data/{v['provider']}/{v['sensor']}", {"limit": 5000, "from": ini.strftime(fmt), "to": ara.strftime(fmt)})
                for o in (j or {}).get("observations", []):
                    obs.setdefault(v["sensor"], []).append((int(o["time"]), o.get("value")))
                n += 1
                time.sleep(0.05)
        print(f"ACA backfill: {n} sensors consultats, {sum(len(x) for x in obs.values())} mesures; noves a l'arxiu: {arxiva(obs, arx, omple=True)}")
        return 0

    obs = llegeix_ultimes()
    if not obs:
        print("ACA: sense dades"); return 1
    noves = arxiva(obs, arx)
    ult = {}
    for sensor, l in obs.items():
        ms, v = max(l)
        ult[sensor] = [datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), num(v) if num(v) is not None else v]
    (sortida / "ultimes.json").write_text(json.dumps({"actualitzat": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "valors": ult},
                                                       ensure_ascii=False, separators=(",", ":")))
    print(f"ACA: {len(cat['estacions'])} estacions, {len(obs)} sensors amb dada, {noves} mesures noves a l'arxiu")
    return 0


if __name__ == "__main__":
    sys.exit(main())
