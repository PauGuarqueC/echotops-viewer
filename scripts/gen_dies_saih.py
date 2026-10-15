#!/usr/bin/env python3
"""Genera data/saih/dies/AAAA-MM-DD.json (dies UTC, graella de 15 min) a partir de l'arxiu ~/saih_arxiu/AAAA-MM.csv.
Format: {"t0":"AAAA-MM-DDT00:00:00Z","pas":15,"v":{senyal:[96 valors|null]}}. Per cubeta de 15 min es desa l'últim valor.
Ús: gen_dies_saih.py [--arxiu ~/saih_arxiu] [--sortida data/saih/dies] [--dies N | --tot]"""
import argparse, csv, json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arxiu', default=str(Path.home() / 'saih_arxiu'))
    ap.add_argument('--sortida', default='data/saih/dies')
    ap.add_argument('--dies', type=int, default=3)
    ap.add_argument('--tot', action='store_true')
    a = ap.parse_args()
    arx, out = Path(a.arxiu).expanduser(), Path(a.sortida); out.mkdir(parents=True, exist_ok=True)
    avui = datetime.now(timezone.utc).date()
    d0 = None if a.tot else avui - timedelta(days=a.dies - 1)
    mesos = sorted(arx.glob('????-??.csv'))
    if d0:
        mesos = [m for m in mesos if m.stem >= d0.strftime('%Y-%m')]
    dies = {}   # 'AAAA-MM-DD' -> {senyal: [96]}
    for m in mesos:
        with m.open(newline='') as fh:
            for r in csv.DictReader(fh):
                try:
                    t = r['temps_utc']; v = float(r['valor'])
                    if not math.isfinite(v): continue
                    d = t[:10]
                    if d0 and d < d0.isoformat(): continue
                    i = int(t[11:13]) * 4 + int(t[14:16]) // 15
                except (KeyError, ValueError, TypeError):
                    continue
                arr = dies.setdefault(d, {}).setdefault(r['sensor'], [None] * 96)
                arr[i] = round(v, 3)
    n = 0
    for d, v in sorted(dies.items()):
        txt = json.dumps({'t0': d + 'T00:00:00Z', 'pas': 15, 'v': v}, separators=(',', ':'))
        f = out / (d + '.json')
        if not f.exists() or f.read_text() != txt:
            f.write_text(txt); n += 1
    print(f'saih dies: {len(dies)} dia(es), {n} escrit(s) a {out}')

if __name__ == '__main__':
    main()
