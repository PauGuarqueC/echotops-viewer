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
TIPUS_EXCLOSOS = {'pluja_dia'}   # l'acumulat del dia es calcula amb l'arxiu

def carrega_senyals(cataleg):
    d = json.loads(Path(cataleg).read_text())
    return {cod: (est, tip) for est, e in d['estacions'].items() for tip, cod in e['senyals'].items() if tip not in TIPUS_EXCLOSOS}

def crida(S, clau, senyals, inicio):
    err = ''
    for intent in (1, 2):
        try:
            r = S.get(B + '/datos/apiopendata', params={'apikey': clau, 'senal': ','.join(senyals), 'inicio': inicio}, timeout=90)
            if r.status_code == 200: return r.json().get('senales', [])
            err = f'HTTP {r.status_code}'
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cataleg', default='data/saih/estacions.json'); ap.add_argument('--sortida', default='data/saih')
    ap.add_argument('--arxiu', default='~/saih_arxiu'); ap.add_argument('--tz', default='Europe/Madrid')
    ap.add_argument('--dies', type=int, default=0, help="a més d'avui, recupera N dies enrere"); ap.add_argument('--forca', action='store_true')
    ap.add_argument('--min-segons', type=int, default=600, help="no torna a demanar si l'última passada és més recent")
    a = ap.parse_args()
    clau = os.environ.get('SAIH_APIKEY')
    if not clau: print('SAIH_APIKEY no definida: salto el col·lector SAIH'); return
    sortida = Path(a.sortida); sortida.mkdir(parents=True, exist_ok=True); uf = sortida / 'ultimes.json'
    anterior = json.loads(uf.read_text()) if uf.exists() else {}
    if not a.forca and not a.dies and time.time() - anterior.get('epoch', 0) < a.min_segons: print('SAIH: passada recent, salto'); return
    tz = ZoneInfo(a.tz); senyals = carrega_senyals(a.cataleg); S = requests.Session(); S.headers['User-Agent'] = 'CTFC visor inundacions (recerca)'
    avui = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    dies = [avui - timedelta(days=n) for n in range(a.dies, -1, -1)]
    files = []
    for i, d in enumerate(dies):
        if i: time.sleep(PAUSA)
        try: fs = dia_files(S, clau, senyals, d, tz)
        except Exception as ex: print('SAIH: error', str(ex).replace(clau, '***')); break
        print(f'  {d:%Y-%m-%d}: {len(fs)} valors'); files += fs
    if not files: print('SAIH: cap valor'); return
    if max(f[1] for f in files) > datetime.now(timezone.utc) + timedelta(hours=1): print("AVÍS: hi ha valors al futur: potser 'fecha' no és hora local (--tz)")
    ult = dict(anterior.get('senyals', {}))
    for cod, t, v in sorted(files, key=lambda x: x[1]):
        ult[cod] = {'t': t.strftime('%Y-%m-%dT%H:%MZ'), 'v': v}
    uf.write_text(json.dumps({'actualitzat': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'epoch': int(time.time()), 'font': 'SAIH Ebre (CHE)', 'senyals': ult}, separators=(',', ':')))
    n = desa_arxiu(files, a.arxiu); print(f'SAIH: {len(ult)} senyals a ultimes.json; {n} valors nous a l\'arxiu')

if __name__ == '__main__': main()
