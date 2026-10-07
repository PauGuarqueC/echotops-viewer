#!/usr/bin/env python3
"""Avisos SMP del Meteocat (episodis oberts + previsió) -> data/smp/avisos.json. Sense historial: cada execució sobreescriu.
Ús: scripts/smp_collector.py [minuts]   (no crida l'API si l'última crida té menys de <minuts>; per defecte 60)"""
import json, os, sys, time, urllib.request, datetime as dt
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data/smp/avisos.json')
STAMP = os.path.expanduser('~/.smp_ultima')
cada = int(sys.argv[1]) if len(sys.argv) > 1 else 60
if os.path.exists(STAMP) and time.time() - os.path.getmtime(STAMP) < cada * 60:
    sys.exit(0)
open(STAMP, 'w').close()
KEY = open(os.path.expanduser('~/.meteocat_key')).read().strip()
URL = 'https://api.meteo.cat/pronostic/v1/smp/episodis-oberts'
UTC = dt.timezone.utc
P = lambda s: dt.datetime.strptime(s, '%Y-%m-%dT%H:%MZ').replace(tzinfo=UTC)
F = lambda d: d.strftime('%Y-%m-%dT%H:%MZ')
d = json.loads(urllib.request.urlopen(urllib.request.Request(URL, headers={'X-Api-Key': KEY}), timeout=30).read())
store = {}
for e in d:
    meteor = e['meteor']['nom']
    for a in sorted(e['avisos'], key=lambda a: a['dataEmisio']):          # de més antic a més nou: el nou substitueix
        em = a['dataEmisio']
        for ev in a['evolucions']:
            dia = P(ev['dia'])
            for pe in ev['periodes']:
                ini = dia + dt.timedelta(hours=int(pe['nom'][:2]))
                af = pe['afectacions'] or []
                key = meteor + '|' + F(ini)
                old = store.get(key)
                if not af and old and old['comarques'] and ini < P(em):
                    continue                                              # període ja passat: un avís nou no l'esborra
                com = dict(old['comarques']) if old and old['emissio'] == em else {}
                for x in af:
                    c = str(x['idComarca'])
                    if c not in com or x['nivell'] > com[c]['nivell']:
                        com[c] = {'nivell': x['nivell'], 'perill': x['perill'], 'llindar': x['llindar']}
                store[key] = {'meteor': meteor, 'ini': F(ini), 'fi': F(ini + dt.timedelta(hours=6)), 'emissio': em, 'comarques': com}
per = sorted((p for p in store.values() if p['comarques']), key=lambda p: (p['ini'], p['meteor']))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + '.tmp'
json.dump({'actualitzat': F(dt.datetime.now(UTC)), 'periodes': per}, open(tmp, 'w'), ensure_ascii=False, separators=(',', ':'))
os.replace(tmp, OUT)
print(len(per), 'períodes amb comarques afectades')
