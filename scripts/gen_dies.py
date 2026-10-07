#!/usr/bin/env python3
"""Arxiu propi d'ACA -> <sortida>/dies/AAAA-MM-DD.json: intensitat (mm/h) cada 5 min (288 passos UTC) de cada pluviometre.
Mateixos sensors i rang valid que aca_pluja.py. null = sense mesura.
Us: scripts/gen_dies.py [tot]   (sense 'tot' nomes regenera avui i ahir, UTC)"""
import argparse, csv, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument('tot', nargs='?')
ap.add_argument('--sortida', default='data/aca')
ap.add_argument('--arxiu', default=str(Path.home() / 'aca_arxiu'))
a = ap.parse_args()
sortida = Path(a.sortida); out = sortida / 'dies'; out.mkdir(parents=True, exist_ok=True)
cat = json.loads((sortida / 'estacions.json').read_text())
sens = {}
for e in cat['estacions']:
    if e['tipus'] == 'pluviometre':
        for v in e['vars']:
            if v.get('unitat') == 'mm/h':
                sens[v['sensor']] = e['id']
avui = datetime.now(timezone.utc).date()
want = None if a.tot == 'tot' else {str(avui - timedelta(days=k)) for k in range(2)}
dies = {}
for f in sorted(Path(a.arxiu).expanduser().glob('*.csv')):
    with open(f, newline='') as fh:
        rd = csv.reader(fh); next(rd, None)
        for r in rd:
            if len(r) < 3 or r[1] not in sens:
                continue
            dia = r[0][:10]
            if want is not None and dia not in want:
                continue
            try:
                idx = int(r[0][11:13]) * 12 + int(r[0][14:16]) // 5; v = float(r[2])
            except ValueError:
                continue
            if 0 <= v <= 400 and 0 <= idx < 288:
                dies.setdefault(dia, {}).setdefault(sens[r[1]], [None] * 288)[idx] = round(v, 1) if v else 0
for dia, est in sorted(dies.items()):
    if len(est) < 20:
        print(dia, 'saltat (', len(est), 'estacions )'); continue
    p = out / (dia + '.json')
    tmp = out / (dia + '.json.tmp')
    tmp.write_text(json.dumps({'dia': dia, 'pas': 5, 'v': est}, separators=(',', ':')))
    os.replace(tmp, p)
    print(dia, len(est), 'estacions,', p.stat().st_size // 1024, 'kB')
