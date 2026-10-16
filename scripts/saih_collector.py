#!/usr/bin/env python3
"""Col·lector SAIH Ebre (API Open Data de la CHE) per a les estacions de data/saih/estacions.json.
- Clau a la variable d'entorn SAIH_APIKEY (mai al codi ni al repositori). Límits de la CHE: 5 crides/minut i <= 100 senyals per crida.
- L'API torna només les 24 h següents a `inicio`: s'hi demana des d'avui a les 00:00 (hora local) -> data/saih/ultimes.json
- Arxiu mensual ~/saih_arxiu/AAAA-MM.csv (temps_utc,sensor,valor), sense duplicats (clau instant+senyal). --dies N recupera N dies enrere.
- `fecha` de l'API es llegeix com a hora local (--tz) i es desa en UTC; si surt al futur, avisa (pot ser que no sigui local)."""
import os, sys, json, time, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

B = 'https://www.saihebro.com'
PAUSA = 13.0          # s entre crides (5/min = 12 s)
MAX_SENYALS = 100
TIPUS_EXCLOSOS = {'pluja_dia', 'volum_pct'}   # l'acumulat del dia es calcula amb l'arxiu; els embassaments encara no es mostren
GRUP_A = ('nivell', 'pluja15')                 # es demanen a cada passada (<= 100 senyals = 1 crida)
ACTIU_S, TRANQUIL_S, CABAL_S = 20 * 60, 60 * 60, 120 * 60   # interval en mode actiu, en mode tranquil, i del cabal (secundari)
RESERVA = 60                                   # a partir d'aquestes crides en 24 h, els intervals es dupliquen (per no esgotar la quota)

def carrega_senyals(cataleg):
    d = json.loads(Path(cataleg).read_text())
    return {cod: (est, tip) for est, e in d['estacions'].items() for tip, cod in e['senyals'].items() if tip not in TIPUS_EXCLOSOS}

# --- Quota de la CHE: 100 crides per 24 h (capçalera RateLimit). L'estat es desa fora del repositori i es respecta entre passades.
QUOTA = Path.home() / '.saih' / 'quota.json'
MAX_DIA = 80          # crides màximes en 24 h (la CHE en permet 100; deixem marge per a proves i recuperacions)

def quota_llegeix():
    try: q = json.loads(QUOTA.read_text())
    except Exception: q = {}
    ara = time.time()
    return {'calls': [t for t in q.get('calls', []) if ara - t < 86400], 'bloc_fins': q.get('bloc_fins', 0)}

def quota_desa(q):
    try: QUOTA.parent.mkdir(parents=True, exist_ok=True); QUOTA.write_text(json.dumps(q))
    except Exception: pass

class Quota(Exception): pass

def crida(S, clau, senyals, inicio):
    err = ''
    for intent in (1, 2):
        q = quota_llegeix()
        if time.time() < q['bloc_fins'] or len(q['calls']) >= MAX_DIA: raise Quota('quota de la CHE esgotada')
        q['calls'].append(time.time()); quota_desa(q)
        try:
            r = S.get(B + '/datos/apiopendata', params={'apikey': clau, 'senal': ','.join(senyals), 'inicio': inicio}, timeout=90)
            if r.status_code == 200: return r.json().get('senales', [])
            if r.status_code == 429:                       # límit superat: no insistir fins que la CHE ho permeti (Retry-After, en segons)
                try: espera = int(r.headers.get('Retry-After', '3600'))
                except ValueError: espera = 3600
                q = quota_llegeix(); q['bloc_fins'] = time.time() + espera + 60; quota_desa(q)
                raise Quota(f'HTTP 429: la CHE demana esperar {espera // 60} min')
            err = f'HTTP {r.status_code}'
        except Quota: raise
        except Exception as ex:
            err = f'{type(ex).__name__}: {str(ex)[:120]}'.replace(clau, '***')
        if intent == 1: print(f'  {err}; reintent en 65 s', flush=True); time.sleep(65)
    raise RuntimeError(err)

def dia_files(S, clau, senyals, dia, tz):
    """Totes les files [(codi, t_utc, valor)] d'un dia local, en crides de <= 100 senyals espaiades."""
    inicio = dia.strftime('%Y-%m-%dT00:00:00'); files = []; cods = list(senyals)
    for i in range(0, len(cods), MAX_SENYALS):
        if i: time.sleep(PAUSA)
        for s in crida(S, clau, cods[i:i + MAX_SENYALS], inicio):
            v = s.get('valor')
            if v is None or v == '': continue
            try: t = datetime.strptime(s['fecha'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz).astimezone(timezone.utc); v = float(v)
            except Exception: continue
            files.append((s['senal'], t, v))
    return files

def desa_arxiu(files, arxiu):
    """Afegeix al CSV mensual només els valors que encara no hi són (clau = instant UTC + senyal), també en reompliments."""
    arxiu = Path(arxiu).expanduser(); arxiu.mkdir(parents=True, exist_ok=True)
    per_mes = {}
    for cod, t, v in sorted(files, key=lambda x: (x[1], x[0])): per_mes.setdefault(t.strftime('%Y-%m'), []).append((cod, t, v))
    n = 0
    for mes, fs in per_mes.items():
        p = arxiu / f'{mes}.csv'; nou = not p.exists(); vistos = set()
        if not nou:
            with open(p, encoding='utf-8') as fh:
                next(fh, None); vistos = {l.rsplit(',', 1)[0] for l in fh}
        with open(p, 'a', encoding='utf-8') as fh:
            if nou: fh.write('temps_utc,sensor,valor\n')
            for cod, t, v in fs:
                k = f'{t.strftime("%Y-%m-%dT%H:%M:%SZ")},{cod}'
                if k in vistos: continue
                fh.write(f'{k},{v:g}\n'); vistos.add(k); n += 1
    return n

def activitat(cat, ul, mov, ara):
    """(actiu, motiu): hi ha raons per actualitzar sovint? Es decideix amb dades locals (sense gastar crides de la CHE):
    tempestes al radar dins la zona de les estacions, pluja recent als pluviòmetres SAIH o un aforador a prop del llindar groc."""
    est = cat['estacions']
    lats = [e['lat'] for e in est.values()]; lons = [e['lon'] for e in est.values()]
    s_, n_, w_, e_ = min(lats) - 0.5, max(lats) + 0.5, min(lons) - 0.5, max(lons) + 0.5
    try:
        m = json.loads(Path(mov).read_text()); cols = m['columnes']; ila, ilo = cols.index('lat'), cols.index('lon')
        for k in sorted(m['frames'])[-4:]:
            if ara - datetime.strptime(k, '%Y%m%d%H%M').replace(tzinfo=timezone.utc).timestamp() > 45 * 60: continue
            if any(s_ <= r[ila] <= n_ and w_ <= r[ilo] <= e_ for r in m['frames'][k]): return True, 'tempesta al radar a la zona'
    except Exception:
        pass
    sen = (ul or {}).get('senyals', {})
    edat = lambda u: ara - datetime.strptime(u['t'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc).timestamp()
    for e in est.values():
        sg = e['senyals']; u = sen.get(sg.get('pluja15'))
        if u and edat(u) < 2 * 3600 and u['v'] >= 0.2: return True, f"pluja recent a {e.get('nom', '?')}"
        ll = (e.get('llindars') or {}).get('nivell'); u = sen.get(sg.get('nivell'))
        if ll and u and edat(u) < 3 * 3600 and u['v'] >= 0.8 * ll[0]: return True, f"nivell a prop del llindar groc a {e.get('nom', '?')}"
    return False, 'sense pluja ni nivells alts'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cataleg', default='data/saih/estacions.json'); ap.add_argument('--sortida', default='data/saih')
    ap.add_argument('--arxiu', default='~/saih_arxiu'); ap.add_argument('--tz', default='Europe/Madrid')
    ap.add_argument('--nowcast', default='data/nowcast/moviment.json', help="moviment de les tempestes (decideix el mode actiu)")
    ap.add_argument('--dies', type=int, default=0, help="a més d'avui, recupera N dies enrere"); ap.add_argument('--forca', action='store_true')
    ap.add_argument('--min-segons', type=int, default=None, help="interval fix entre passades (si no, adaptatiu: 20 min amb activitat, 60 min si no)")
    a = ap.parse_args()
    clau = os.environ.get('SAIH_APIKEY')
    if not clau: print('SAIH_APIKEY no definida: salto el col·lector SAIH'); return
    sortida = Path(a.sortida); sortida.mkdir(parents=True, exist_ok=True); uf = sortida / 'ultimes.json'
    anterior = json.loads(uf.read_text()) if uf.exists() else {}
    q = quota_llegeix()
    if time.time() < q['bloc_fins']: print(f"SAIH: bloquejat per la CHE fins d'aquí {int((q['bloc_fins'] - time.time()) / 60)} min, salto"); return
    if len(q['calls']) >= MAX_DIA: print(f"SAIH: {len(q['calls'])} crides en 24 h (màxim {MAX_DIA}), salto"); return
    cat = json.loads(Path(a.cataleg).read_text())
    actiu, motiu = activitat(cat, anterior, a.nowcast, time.time())
    interval = a.min_segons if a.min_segons is not None else (ACTIU_S if actiu else TRANQUIL_S)
    if len(q['calls']) >= RESERVA: interval *= 2
    if not a.forca and not a.dies and time.time() - anterior.get('epoch', 0) < interval - 240:
        print(f"SAIH: mode {'actiu' if actiu else 'tranquil'} ({motiu}); passada recent, salto"); return
    tz = ZoneInfo(a.tz); totes = carrega_senyals(a.cataleg); S = requests.Session(); S.headers['User-Agent'] = 'CTFC visor inundacions (recerca)'
    cabal = a.forca or a.dies or time.time() - anterior.get('epoch_cabal', 0) >= CABAL_S - 240
    senyals = {c: v for c, v in totes.items() if v[1] in GRUP_A or (cabal and v[1] == 'cabal')}
    print(f"SAIH: mode {'actiu' if actiu else 'tranquil'} ({motiu}); {len(senyals)} senyals{' amb cabal' if cabal else ''}")
    avui = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    if not a.dies and anterior.get('epoch') and datetime.fromtimestamp(anterior['epoch'], tz).date() < avui.date():
        a.dies = 1                                          # la darrera passada és d'un dia anterior (p. ex. després d'un bloqueig): es recupera també ahir
    dies = [avui - timedelta(days=n) for n in range(a.dies, -1, -1)]
    files = []
    for i, d in enumerate(dies):
        if i: time.sleep(PAUSA)
        try: fs = dia_files(S, clau, senyals, d, tz)
        except Quota as ex: print('SAIH:', ex); break
        except Exception as ex: print('SAIH: error', str(ex).replace(clau, '***')); break
        print(f'  {d:%Y-%m-%d}: {len(fs)} valors'); files += fs
    if not files: print('SAIH: cap valor'); return
    if max(f[1] for f in files) > datetime.now(timezone.utc) + timedelta(hours=1): print("AVÍS: hi ha valors al futur: potser 'fecha' no és hora local (--tz)")
    ult = dict(anterior.get('senyals', {}))
    for cod, t, v in sorted(files, key=lambda x: x[1]):
        ult[cod] = {'t': t.strftime('%Y-%m-%dT%H:%MZ'), 'v': v}
    uf.write_text(json.dumps({'actualitzat': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'epoch': int(time.time()),
                              'epoch_cabal': int(time.time()) if cabal else anterior.get('epoch_cabal', 0), 'font': 'SAIH Ebre (CHE)', 'senyals': ult}, separators=(',', ':')))
    n = desa_arxiu(files, a.arxiu); print(f'SAIH: {len(ult)} senyals a ultimes.json; {n} valors nous a l\'arxiu')

if __name__ == '__main__': main()
