#!/usr/bin/env python3
"""Avisos SMP del Meteocat -> data/smp/avisos.json (amb historial) + arxiu cru a ~/smp_arxiu."""
import json, os, hashlib, urllib.request, datetime as dt
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data/smp/avisos.json')
ARX = os.path.expanduser('~/smp_arxiu')
import sys, time
_st = os.path.expanduser('~/smp_arxiu/.ultima')
_cada = int(sys.argv[1]) if len(sys.argv) > 1 else 60
if os.path.exists(_st) and time.time() - os.path.getmtime(_st) < _cada * 60:
    sys.exit(0)
os.makedirs(os.path.dirname(_st), exist_ok=True); open(_st, 'w').close()
KEY = open(os.path.expanduser('~/.meteocat_key')).read().strip()
URL = 'https://api.meteo.cat/pronostic/v1/smp/episodis-oberts'
UTC = dt.timezone.utc
P = lambda s: dt.datetime.strptime(s, '%Y-%m-%dT%H:%MZ').replace(tzinfo=UTC)
F = lambda d: d.strftime('%Y-%m-%dT%H:%MZ')
raw = urllib.request.urlopen(urllib.request.Request(URL, headers={'X-Api-Key': KEY}), timeout=30).read()
d = json.loads(raw)
now = dt.datetime.now(UTC)
os.makedirs(ARX, exist_ok=True)
h = hashlib.sha1(raw).hexdigest()
hp = os.path.join(ARX, '.last')
if not os.path.exists(hp) or open(hp).read() != h:
    dd = os.path.join(ARX, now.strftime('%Y-%m-%d')); os.makedirs(dd, exist_ok=True)
    open(os.path.join(dd, now.strftime('%H%M') + '.json'), 'wb').write(raw)
    open(hp, 'w').write(h)
store = {}
if os.path.exists(OUT):
    for p in json.load(open(OUT)).get('periodes', []):
        store[p['meteor'] + '|' + p['ini']] = p
for e in d:
    meteor = e['meteor']['nom']
    for a in e['avisos']:
        em = a['dataEmisio']
        for ev in a['evolucions']:
            dia = P(ev['dia'])
            for pe in ev['periodes']:
                ini = dia + dt.timedelta(hours=int(pe['nom'][:2]))
                fi = ini + dt.timedelta(hours=6)
                af = pe['afectacions'] or []
                key = meteor + '|' + F(ini)
                old = store.get(key)
                if old and old['emissio'] > em:
                    continue
                if not af and old and old['comarques'] and ini < P(em):
                    continue  # període ja passat: un avís nou no l'esborra
                com = dict(old['comarques']) if old and old['emissio'] == em else {}
                for x in af:
                    c = str(x['idComarca'])
                    if c not in com or x['nivell'] > com[c]['nivell']:
                        com[c] = {'nivell': x['nivell'], 'perill': x['perill'], 'llindar': x['llindar']}
                if com or old:
                    store[key] = {'meteor': meteor, 'ini': F(ini), 'fi': F(fi), 'emissio': em, 'comarques': com}
lim = F(now - dt.timedelta(days=60))
per = sorted((p for p in store.values() if p['ini'] >= lim), key=lambda p: (p['ini'], p['meteor']))
tmp = OUT + '.tmp'
json.dump({'actualitzat': F(now), 'periodes': per}, open(tmp, 'w'), ensure_ascii=False, separators=(',', ':'))
os.replace(tmp, OUT)
print(len(per), 'períodes;', sum(1 for p in per if p['comarques']), 'amb comarques afectades')
