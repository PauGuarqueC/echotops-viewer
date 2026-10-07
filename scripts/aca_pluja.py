#!/usr/bin/env python3
"""Pluja acumulada (30 min i 3 h) dels pluviòmetres de l'ACA i nivell d'avís, a partir de l'arxiu propi del col·lector.
Entrada:  ~/aca_arxiu/AAAA-MM.csv  +  <sortida>/estacions.json     Sortida: <sortida>/pluja.json
Els pluviòmetres de l'ACA donen la intensitat (mm/h) cada 5 min; cada mesura es pren com la mitjana dels 5 min anteriors,
de manera que l'acumulat = suma(intensitat) / 12.
Nivells: 1 groc = llindar baix en 30 min o en 3 h · 2 taronja = llindar alt en un dels dos · 3 vermell = llindar alt en els dos.
Ús: venv/bin/python scripts/aca_pluja.py --sortida data/aca"""
import argparse, csv, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LL30 = (20.0, 40.0)        # mm / 30 min (baix, alt)
LL3H = (60.0, 90.0)        # mm / 3 h   (baix, alt)
PAS = 5                    # min entre mesures
MAX_EDAT = 30              # min: si l'última mesura és més antiga, l'estació es considera sense dada


def nivell(a30, a3h):
    h30, h3 = a30 > LL30[1], a3h > LL3H[1]
    if h30 and h3:
        return 3
    if h30 or h3:
        return 2
    if a30 > LL30[0] or a3h > LL3H[0]:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sortida", default="data/aca")
    ap.add_argument("--arxiu", default=str(Path.home() / "aca_arxiu"))
    a = ap.parse_args()
    sortida, arx = Path(a.sortida), Path(a.arxiu).expanduser()
    try:
        cat = json.loads((sortida / "estacions.json").read_text())
    except Exception:
        print("ACA pluja: falta estacions.json (executa abans aca_collector.py)"); return 1

    sens = {}                                                              # sensor -> estació
    for e in cat["estacions"]:
        if e["tipus"] == "pluviometre":
            for v in e["vars"]:
                if v.get("unitat") == "mm/h":
                    sens[v["sensor"]] = e
    ara = datetime.now(timezone.utc)
    ini = ara - timedelta(hours=3, minutes=10)
    mesos = sorted({f"{t:%Y-%m}" for t in (ini, ara)})
    ser = {}                                                               # sensor -> {datetime: mm/h}
    for m in mesos:
        f = arx / f"{m}.csv"
        if not f.exists():
            continue
        with open(f, newline="") as fh:
            rd = csv.reader(fh); next(rd, None)
            for r in rd:
                if len(r) < 3 or r[1] not in sens:
                    continue
                try:
                    t = datetime.strptime(r[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc); v = float(r[2])
                except ValueError:
                    continue
                if t >= ini and 0 <= v <= 400:                             # rang vàlid del sensor
                    ser.setdefault(r[1], {})[t] = v

    out = []
    for s, e in sens.items():
        d = ser.get(s)
        if not d:
            out.append({"id": e["id"], "nom": e["nom"], "comarca": e.get("comarca"), "lat": e["lat"], "lon": e["lon"], "t": None, "i": None,
                        "a30": None, "a3h": None, "n": 0, "nivell": 0})
            continue
        tl = max(d)
        edat = (ara - tl).total_seconds() / 60
        def acum(minuts):
            lim = tl - timedelta(minutes=minuts)
            xs = [v for t, v in d.items() if t > lim]
            return round(sum(xs) * PAS / 60, 1), len(xs)
        a30, n30 = acum(30); a3h, n3h = acum(180)
        viu = edat <= MAX_EDAT
        out.append({"id": e["id"], "nom": e["nom"], "comarca": e.get("comarca"), "lat": e["lat"], "lon": e["lon"],
                    "t": tl.strftime("%Y-%m-%dT%H:%MZ"), "i": d[tl], "a30": a30, "a3h": a3h, "n": n3h, "nivell": nivell(a30, a3h) if viu else 0})
    res = {"actualitzat": ara.strftime("%Y-%m-%dT%H:%M:%SZ"), "llindars": {"30min": LL30, "3h": LL3H}, "estacions": out}
    (sortida / "pluja.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    nv = [x["nivell"] for x in out]
    print(f"ACA pluja: {len(out)} pluviòmetres · nivell 1/2/3: {nv.count(1)}/{nv.count(2)}/{nv.count(3)} · màxim 30 min: {max([x['a30'] or 0 for x in out], default=0)} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
