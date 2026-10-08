#!/usr/bin/env python3
"""Avisos SMP del Meteocat (vigents + previsió) -> data/smp/avisos.json. Sense historial: només trams que encara no han acabat.
Una execució = DIES crides a l'API (v2 episodis-oberts?data=...). Ús: scripts/smp_collector.py [minuts]  (per defecte 360)"""
import json, os, sys, time, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
DIES = 3                                                   # avui + 2 dies més
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data/smp/avisos.json')
STAMP = os.path.expanduser('~/.smp_ultima')
cada = int(sys.argv[1]) if len(sys.argv) > 1 else 360
if os.path.exists(STAMP) and time.time() - os.path.getmtime(STAMP) < cada * 60:
    sys.exit(0)
open(STAMP, 'w').close()
KEY = open(os.path.expanduser('~/.meteocat_key')).read().strip()
UTC = dt.timezone.utc
P = lambda s: dt.datetime.strptime(s, '%Y-%m-%dT%H:%MZ').replace(tzinfo=UTC)
F = lambda d: d.strftime('%Y-%m-%dT%H:%MZ')
avui = dt.datetime.now(ZoneInfo('Europe/Madrid')).date()
resp, errors = [], 0
for k in range(DIES):
    dia = avui + dt.timedelta(days=k)
    url = 'https://api.meteo.cat/pronostic/v2/smp/episodis-oberts?data=%sZ' % dia.isoformat()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={'X-Api-Key': KEY}), timeout=30).read())
        print(dia, ':', len(r), 'episodis'); resp += r
    except Exception as e:
        errors += 1; print(dia, 'error:', str(e)[:80])
if errors == DIES:
    sys.exit('Cap crida ha funcionat; no sobreescric avisos.json')
items = sorted(((a['dataEmisio'], e['meteor']['nom'], a) for e in resp for a in e['avisos']), key=lambda t: t[0])
store = {}
for em, meteor, a in items:                                   # de més antic a més nou: el nou substitueix
    for ev in a['evolucions']:
        dia = P(ev['dia'])
        for pe in ev['periodes']:
            ini = dia + dt.timedelta(hours=int(pe['nom'][:2]))
            af = pe['afectacions'] or []
            key = meteor + '|' + F(ini)
            old = store.get(key)
            if not af and old and old['comarques'] and ini < P(em):
                continue                                      # període ja passat: un avís nou no l'esborra
            com = dict(old['comarques']) if old and old['emissio'] == em else {}
            for x in af:
                c = str(x['idComarca'])
                if c not in com or x['nivell'] > com[c]['nivell']:
                    com[c] = {'nivell': x['nivell'], 'perill': x['perill'], 'llindar': x['llindar']}
            store[key] = {'meteor': meteor, 'ini': F(ini), 'fi': F(ini + dt.timedelta(hours=6)), 'emissio': em, 'comarques': com}
ara = F(dt.datetime.now(UTC))
per = sorted((p for p in store.values() if p['comarques'] and p['fi'] > ara), key=lambda p: (p['ini'], p['meteor']))
per = [p for p in per if any(k in p['meteor'].lower() for k in ('pluja', 'temps violent', 'neu'))]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + '.tmp'
json.dump({'actualitzat': ara, 'periodes': per}, open(tmp, 'w'), ensure_ascii=False, separators=(',', ':'))
os.replace(tmp, OUT)
print(len(per), 'períodes vigents o de previsió' + (' · fins a ' + max(p['fi'] for p in per) if per else ''))
