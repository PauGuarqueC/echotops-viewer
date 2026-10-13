#!/usr/bin/env python3
"""Arxiu propi d'ACA -> <sortida>/dies_afo/AAAA-MM-DD.json: cabal (m³/s) i nivell (cm) dels aforadors amb llindars, en una graella de 5 min (288 passos UTC).
Els sensors surten de <sortida>/llindars.json (camps sq = cabal, sh = nivell). null = sense mesura (alguns sensors mostregen cada 10-15 min).
Ús: scripts/gen_dies_afo.py            (regenera avui i ahir, UTC)
    scripts/gen_dies_afo.py tot        (els últims 14 dies de l'arxiu; amb --dies N, els últims N)"""
import argparse, csv, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("tot", nargs="?")
ap.add_argument("--sortida", default="data/aca")
ap.add_argument("--arxiu", default=str(Path.home() / "aca_arxiu"))
ap.add_argument("--dies", type=int, default=None)
a = ap.parse_args()
sortida = Path(a.sortida); out = sortida / "dies_afo"; out.mkdir(parents=True, exist_ok=True)
try:
    LL = json.loads((sortida / "llindars.json").read_text())["estacions"]
except Exception:
    print("ACA aforadors: falta llindars.json (executa abans aca_collector.py)"); raise SystemExit(1)
sq, sh = {}, {}
for codi, l in LL.items():
    if l.get("sq"): sq[l["sq"]] = codi
    if l.get("sh"): sh[l["sh"]] = codi
n = a.dies if a.dies else (14 if a.tot == "tot" else 2)
avui = datetime.now(timezone.utc).date()
want = {str(avui - timedelta(days=k)) for k in range(n)}
dies = {}
for f in sorted(Path(a.arxiu).expanduser().glob("*.csv")):
    if f.stem[:7] not in {d[:7] for d in want}:
        continue
    with open(f, newline="") as fh:
        rd = csv.reader(fh); next(rd, None)
        for r in rd:
            if len(r) < 3 or (r[1] not in sq and r[1] not in sh) or r[0][:10] not in want:
                continue
            try:
                idx = int(r[0][11:13]) * 12 + int(r[0][14:16]) // 5; v = float(r[2])
            except ValueError:
                continue
            if not 0 <= idx < 288:
                continue
            d = dies.setdefault(r[0][:10], {"q": {}, "h": {}})
            if r[1] in sq:
                if -0.5 <= v <= 100000:                                   # cabal: s'ignoren valors absurds i els negatius petits es porten a 0
                    d["q"].setdefault(sq[r[1]], [None] * 288)[idx] = round(max(v, 0), 3)
            elif -50 <= v <= 5000:                                        # nivell (cm)
                d["h"].setdefault(sh[r[1]], [None] * 288)[idx] = round(v, 1)
for dia, d in sorted(dies.items()):
    if len(d["q"]) < 10:
        print(dia, "saltat (", len(d["q"]), "estacions )"); continue
    p = out / (dia + ".json"); tmp = out / (dia + ".json.tmp")
    tmp.write_text(json.dumps({"dia": dia, "pas": 5, "q": d["q"], "h": d["h"]}, separators=(",", ":")))
    os.replace(tmp, p)
    print(dia, len(d["q"]), "estacions de cabal,", p.stat().st_size // 1024, "kB")
