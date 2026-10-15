#!/usr/bin/env python3
"""Catàleg SAIH Ebre (es fa un sol cop): estacions de les conques d'interès (Garona, Noguera, Segre, Baix Ebre) amb
aforadors (nivell NRIO, cabal QRIO), pluviòmetres (PQUIN cada 15 min, PACUM dia) i embassaments (% volum PORCE),
amb coordenades i llindars d'avís -> data/saih/estacions.json
Totes les fonts són públiques: arbre de senyals (~/saih_recon/arbre.json, o SAIH_USER/SAIH_PASS), /api/info/getTablaUmbrales
i la fitxa /api/ficha/procesarTablaInfoGeneral (porta riu i coordenades; 1 petició/s; es desa a ~/saih_recon/fitxes.json i es reprèn)."""
import os, re, sys, json, time, argparse, unicodedata
from datetime import datetime, timezone
from pathlib import Path
import requests

B = 'https://www.saihebro.com'
TIPUS = {'NRIO': 'nivell', 'QRIO': 'cabal', 'PORCE': 'volum_pct', 'PQUIN': 'pluja15', 'PACUM': 'pluja_dia'}
# Conca segons el RIU de la fitxa (nom sense accents, majúscules). L'Ebre només tram baix (lon >= 0,2 i lat <= 41,5)
RIUS = [('Garona', r'GARONA|BALARTIAS|VALARTIES'), ('Noguera', r'NOGUERA|RIBAGORZ|PALLARES|FLAMISELL|CARDOS|SENET|MANYANET|LLAUSET|ESTAHON|ESTAON|VALLFARRERA|ESCRITA'), ('Segre', r'SEGRE|VALIRA|\bSIO\b|SIOS|CERVERA|RIALB|\bCORP\b|\bCORB\b'),
        ('Baix Ebre', r'^EBRO$|^EBRE$|CIURANA|SIURANA|ALGAS|ALGARS|CANALETA|ASMAT')]
# Preselecció d'aforadors i embassaments pel nom de la senyal (per no baixar la fitxa de les ~700 estacions de tota la conca)
NOMS = r'GARONA|BOSSOST|ARTIES|PONT DE REI|\bARAN\b|NOGUERA|RIBAGORZ|PALLARES|FLAMISELL|CARDOS|LLAVORSI|SENET|TALARN|TERRADETS|CAMARASA|SAN LORENZO|ESCALES|CANELLES|SANTA ANA|CAVALLERS|BASERCA|LLAUSET|SEGRE|VALIRA|SIOS|OLIANA|RIALB|ORGANA|ISOVOL|TORREBLANCA|EBRO EN (ASCO|XERTA|TORTOSA|FLIX|MEQUINENZA|RIBARROJA|MORA|SASTAGO)|EBRO.*SASTAGO|EMBALSE DE (FLIX|MEQUINENZA|RIBARROJA)'

def net(t): return ''.join(c for c in unicodedata.normalize('NFD', (t or '').upper().strip()) if unicodedata.category(c) != 'Mn')

def conca_rio(rio, lat, lon):
    n = net(rio)
    for c, pat in RIUS:
        if re.search(pat, n):
            if c == 'Baix Ebre' and not (lon >= 0.2 and lat <= 41.5): return None
            return c
    return None

def senyals_arbre(arbre):
    """{estacio: {nom_senyal, senyals:{tipus: codi}}} per als tipus d'interès; aforadors/embassaments preseleccionats pel nom"""
    est = {}
    for x in arbre:
        tip = x.get('data', {}).get('LS_TIPO_SENAL'); txt = x['text']
        if tip not in TIPUS or '(HIST)' in txt.upper(): continue
        if tip in ('NRIO', 'QRIO', 'PORCE') and not re.search(NOMS, net(txt)): continue
        e = est.setdefault(x['id'][:4], {'nom_senyal': txt.split(' - ', 1)[-1].strip().rstrip('.'), 'senyals': {}})
        k = TIPUS[tip]
        if k not in e['senyals'] or ('TOTAL' not in txt.upper() and x['id'].endswith('1')): e['senyals'][k] = x['id']
    return {c: e for c, e in est.items() if set(e['senyals']) & {'nivell', 'cabal', 'volum_pct', 'pluja15'}}

def camp(h, etiqueta):
    m = re.search(r'<td>\s*' + etiqueta + r'\s*</td>\s*<td>\s*([^<]*?)\s*</td>', h, re.I)
    return m.group(1).strip() if m else ''

def fitxa(S, est):
    r = S.get(f'{B}/api/ficha/procesarTablaInfoGeneral', params={'estacion': est}, timeout=60)
    h = r.json().get('INFO_GENERAL', '') if r.ok else ''
    la, lo = re.search(r"data-lat='([\d.\-]+)'", h), re.search(r"data-lng='([\d.\-]+)'", h)
    if not (la and lo): return None
    return {'nom': camp(h, r'Descripci[oó]n'), 'rio': camp(h, r'R[ií]o'), 'ccaa': camp(h, r'Comunidad Aut[oó]noma'),
            'prov': camp(h, r'Provincia'), 'pobl': camp(h, r'Poblaci[oó]n'), 'lat': float(la.group(1)), 'lon': float(lo.group(1))}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--sortida', default='data/saih/estacions.json')
    ap.add_argument('--arbre', default=str(Path.home() / 'saih_recon' / 'arbre.json'))
    ap.add_argument('--cache', default=str(Path.home() / 'saih_recon' / 'fitxes.json')); a = ap.parse_args()
    S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (CTFC visor inundacions)', 'X-Requested-With': 'XMLHttpRequest'})
    if Path(a.arbre).exists(): arbre = json.loads(Path(a.arbre).read_text())
    else:
        u, p = os.environ.get('SAIH_USER'), os.environ.get('SAIH_PASS')
        if not (u and p): sys.exit("Falta l'arbre de senyals (%s) o SAIH_USER/SAIH_PASS" % a.arbre)
        S.post(B + '/api/usuarios/login', json={'formUsuario': u, 'formContrasena': p}, timeout=40)
        arbre = S.get(B + '/api/opendata/getListaSenalesArbol', timeout=90).json()
    est = senyals_arbre(arbre)
    umb = {x['codigo']: x for x in S.get(B + '/api/info/getTablaUmbrales', timeout=90).json()}
    cp = Path(a.cache); cache = json.loads(cp.read_text()) if cp.exists() else {}
    falten = [c for c in sorted(est) if c not in cache]
    print(f'{len(est)} estacions candidates; {len(falten)} fitxes per baixar (~1 s cadascuna)...')
    for i, c in enumerate(falten):
        try: cache[c] = fitxa(S, c) or {'buida': True}
        except Exception as ex: print('  error', c, ex); continue
        time.sleep(1.0)
        if (i + 1) % 25 == 0: cp.parent.mkdir(parents=True, exist_ok=True); cp.write_text(json.dumps(cache)); print(f'  {i+1}/{len(falten)}')
    cp.parent.mkdir(parents=True, exist_ok=True); cp.write_text(json.dumps(cache))
    sortida, fora, dubt = {}, {}, []
    for c, e in sorted(est.items()):
        f = cache.get(c)
        if not f or f.get('buida'): continue
        cn = conca_rio(f['rio'], f['lat'], f['lon'])
        if not cn:
            fora[f['rio'] or '?'] = fora.get(f['rio'] or '?', 0) + 1
            if 40.45 <= f['lat'] <= 42.95 and 0.15 <= f['lon'] <= 2.30: dubt.append((c, f['rio'], f['nom'] or e['nom_senyal'], f['lat'], f['lon']))
            continue
        ll = {}
        for k, cod in e['senyals'].items():
            u = umb.get(cod)
            if u and None not in (u.get('col1'), u.get('col2'), u.get('col3')): ll[k] = [u['col1'], u['col2'], u['col3']]
        sortida[c] = {'nom': f['nom'] or e['nom_senyal'], 'rio': f['rio'], 'conca': cn, 'ccaa': f['ccaa'], 'prov': f['prov'], 'pobl': f['pobl'],
                      'lat': f['lat'], 'lon': f['lon'], 'senyals': e['senyals'], 'llindars': ll}
    Path(a.sortida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.sortida).write_text(json.dumps({'actualitzat': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'font': 'SAIH Ebre (CHE)', 'estacions': sortida}, ensure_ascii=False, separators=(',', ':')))
    per = {}
    for v in sortida.values(): per.setdefault(v['conca'], []).append(v)
    for cn, v in per.items():
        n = lambda k: sum(1 for z in v if k in z['senyals'])
        print(f'{cn}: {len(v)} estacions · {n("nivell")} nivell · {n("cabal")} cabal · {n("pluja15")} pluja · {n("volum_pct")} embassament · {sum(1 for z in v if z["llindars"])} amb llindars')
    print('desat', a.sortida, '·', len(sortida), 'estacions')
    print('Estacions descartades DINS de la zona (codi, riu, lat/lon, nom) - per revisar:')
    for c, rio, nom, la, lo in sorted(dubt, key=lambda z: (z[1] or '', z[0])): print(f'  {c} {(rio or "?"):20} {la:.2f},{lo:.2f} {nom[:42]}')
    print('Rius descartats (per revisar si en falta algun):', ', '.join(f'{k} ({v})' for k, v in sorted(fora.items(), key=lambda kv: -kv[1])[:40]))

if __name__ == '__main__': main()
