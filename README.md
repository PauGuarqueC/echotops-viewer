# Meteo · Inundacions

Visor web de seguiment d'episodis de pluja i inundacions a Catalunya per a Bombers (DECGOE).
Combina radar, models de previsió i aforadors/pluviòmetres en un sol mapa amb barra de temps.

## Què mostra

| Capa | Font | Freqüència |
| --- | --- | --- |
| Echotops | Meteocat (SFTP) | 6 min |
| Reflectivitat i pluja OPERA | EUMETNET OPERA (bucket S3 públic) | 5 min |
| Tempestes enganxades (nowcast) | Calculat a partir d'OPERA | 5 min |
| Satèl·lit MTG IR10.5 | EUMETSAT (WMS, des del navegador) | 10 min |
| Pluja prevista WRF-SMC, AROME, ICON-EU | Servidor labfire / Météo-France | Per run |
| Pluviòmetres i aforadors ACA | ACA (Sentilo) | 5 min |
| Pluviòmetres i aforadors SAIH Ebre | CHE (Open Data) | 15 min |
| Avisos SMP | Meteocat (API) | 6 h |

## Com funciona

Cada 5 minuts el cron de labfire executa `update.sh`, que:

1. Baixa i processa les dades de cada font (`scripts/`).
2. Escriu el que llegeix el visor a la carpeta d'**outputs**.
3. Mentre el visor es publiqui a GitHub Pages (`INUND_GIT_PUSH=1`): copia els outputs a `data/`
   dins del repo i en fa `git commit` + `git push`.

Si una font falla, el cicle continua amb les altres i deixa una línia `<font>: error` a `update.log`.
Si fallen els echotops, s'atura el cicle sencer.

## Carpetes al servidor

```
/home/labfire/visors/
    scripts/inundacions/     <- aquest repo (codi), venv/, config.env, update.log
    inputs/
        echotops/            <- TIFF bruts del Meteocat (raw/) i cache de costa
        opera/               <- OPERA: brut/ (.h5, 3 h) i arxiu_1km/ (5 dies)
        aca/                 <- històric ACA (CSV mensual) i estat .ultim.json
        saih/                <- històric SAIH (CSV mensual); recon/ per refer el catàleg
        arome/               <- pluja AROME baixada
    outputs/inundacions/     <- tot el que llegeix el visor (el que s'ha de servir com a data/)
```

Els models WRF-SMC i ICON-EU es llegeixen directament de `/home/labfire/data/`.

Les rutes es configuren a `config.env` (fora del git; plantilla a `config.env.example`) i les fan
servir `update.sh` i `scripts/rutes.py`. Sense `config.env`, es fan servir les rutes antigues del
home de l'usuari.

## Credencials

No n'hi ha cap dins del repo. Viuen al home de l'usuari que executa el cron:

| Fitxer | Per a |
| --- | --- |
| `~/.config/echotops.env` | SFTP del Meteocat |
| `~/.meteocat_key` | API del Meteocat (avisos SMP) |
| `~/.arome_oauth` | API de Météo-France (AROME) |
| `~/.saih/env` | API Open Data de la CHE (SAIH) |

Fitxers d'estat, també al home: `~/.saih/quota.json` (consum de la CHE) i `~/.smp_ultima`
(última consulta SMP).

## Posar-lo en marxa

```bash
cd /home/labfire/visors/scripts/inundacions
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp config.env.example config.env      # i adaptar les rutes
./update.sh                           # prova a mà
```

Cron (usuari que té les credencials):

```
1-59/5 * * * * flock -n /tmp/echotops_update.lock /home/labfire/visors/scripts/inundacions/update.sh >> /home/labfire/visors/scripts/inundacions/update.log 2>&1
```

`paramiko` ha de ser la 3.4.0: el servidor SFTP del Meteocat fa servir claus `ssh-rsa` antigues.

## Scripts principals

| Script | Fa |
| --- | --- |
| `descarrega_echotops_sftp.py`, `process_tiffs.py`, `build_manifest.py` | Echotops: baixada, PNG i llista de fotogrames |
| `opera_collector.py`, `opera_a_arxiu.py` | OPERA: PNG per al visor i arxiu a 1 km |
| `nowcast_export.py` (+ `nowcast.py`, `persist.py`) | Detecció de tempestes enganxades |
| `arome_precip.py`, `models_export.py` (+ `icon_export.py`) | Pluja prevista dels models |
| `aca_collector.py`, `aca_pluja.py`, `gen_dies.py`, `gen_dies_afo.py` | ACA |
| `saih_collector.py`, `gen_dies_saih.py` | SAIH Ebre |
| `smp_collector.py` | Avisos SMP |
| `saih_cataleg.py`, `rius_build.py` | Catàlegs i capes fixes (s'executen a mà, un sol cop) |
| `rutes.py` | Rutes de dades, llegides de `config.env` |

## Migració a la plataforma de Lab-fire

Quan la plataforma serveixi `outputs/inundacions/` directament:

1. `INUND_GIT_PUSH=0` a `config.env` (deixa de copiar dades al repo i de fer push).
2. Esborrar `data/` del repo.
3. Començar un historial nou només amb codi al repositori de Lab-fire.
