#!/bin/bash
cd "$(dirname "$0")"
# retall del log: es queda amb les últimes 5000 línies si passa de 20 MB
[ -f update.log ] && [ "$(stat -c%s update.log)" -gt 20000000 ] && tail -5000 update.log > /tmp/update_log_tmp && cat /tmp/update_log_tmp > update.log
set -e

if [ -f venv/bin/activate ]; then
  source venv/bin/activate
fi

# --- Rutes (config.env; sense config.env, les d'abans de la migració) ---
if [ -f config.env ]; then
  set -a; source config.env; set +a
fi
WEB="${INUND_WEB:-$PWD/data}"
ECHOTOPS="${INUND_ECHOTOPS:-$HOME/echotops-data}"
PNG="${INUND_PNG:-$ECHOTOPS/png}"
RADAR="${INUND_RADAR:-$ECHOTOPS/radar}"
ACA_ARXIU="${INUND_ACA_ARXIU:-$HOME/aca_arxiu}"
SAIH_ARXIU="${INUND_SAIH_ARXIU:-$HOME/saih_arxiu}"
AROME="${INUND_AROME:-$HOME/arome_precip}"
WRF="${INUND_WRF:-/home/labfire/data/SMC-WRF}"
GIT_PUSH="${INUND_GIT_PUSH:-1}"
export INUND_WEB="$WEB" INUND_ECHOTOPS="$ECHOTOPS" INUND_PNG="$PNG" INUND_RADAR="$RADAR"

# --- Echotops (Meteocat SFTP) ---
python3 scripts/descarrega_echotops_sftp.py
python3 scripts/process_tiffs.py
python3 scripts/build_manifest.py
if [ "$(realpath -m "$PNG")" != "$(realpath -m "$WEB/png")" ]; then
  rsync -a "$PNG/" "$WEB/png/"
fi

# --- Nowcasting: tempestes enganxades (OPERA) ---
python3 scripts/opera_collector.py || echo "opera: error" >&2
python3 scripts/opera_a_arxiu.py --hores 3 --pas 5 --sortida "$RADAR/arxiu_1km" || echo "opera arxiu: error" >&2
python3 scripts/nowcast_export.py --arrel "$RADAR/arxiu_1km" --sortida "$WEB/nowcast" --no-refl || echo "nowcast: error a l'exportació" >&2

# --- Previsió: WRF-SMC i AROME (pluja de Météo-France) ---
python3 scripts/arome_precip.py --sortida "$AROME" || echo "arome: error a la descàrrega" >&2
python3 scripts/models_export.py --wrf-dir "$WRF" --arome-dir "$AROME" --sortida "$WEB/models" || echo "models: error a l'exportació" >&2

# --- ACA ---
python3 scripts/aca_collector.py --sortida "$WEB/aca" --arxiu "$ACA_ARXIU" || echo "aca: error" >&2
python3 scripts/aca_pluja.py --sortida "$WEB/aca" --arxiu "$ACA_ARXIU" || echo "aca pluja: error" >&2
python3 scripts/gen_dies.py --sortida "$WEB/aca" --arxiu "$ACA_ARXIU" || echo "aca dies: error" >&2
python3 scripts/gen_dies_afo.py --sortida "$WEB/aca" --arxiu "$ACA_ARXIU" || echo "aca dies afo: error" >&2

# --- SAIH Ebre ---
if [ -f "$HOME/.saih/env" ]; then
  source "$HOME/.saih/env"
  python3 scripts/saih_collector.py --cataleg "$WEB/saih/estacions.json" --sortida "$WEB/saih" \
    --arxiu "$SAIH_ARXIU" --nowcast "$WEB/nowcast/moviment.json" || echo "saih: error" >&2
  python3 scripts/gen_dies_saih.py --arxiu "$SAIH_ARXIU" --sortida "$WEB/saih/dies" --dies 3 || echo "saih dies: error" >&2
fi

# --- Avisos SMP ---
python3 scripts/smp_collector.py 360 || echo "smp: error" >&2

# --- Publicació a GitHub Pages (només fins que la plataforma d'IT funcioni) ---
if [ "$GIT_PUSH" = "1" ]; then
  if [ "$(realpath -m "$WEB")" != "$(realpath -m data)" ]; then
    if [ -f "$WEB/png/manifest.json" ]; then
      rsync -a --delete "$WEB/" data/
    else
      echo "ATENCIÓ: $WEB no té png/manifest.json; no copio res cap a data/ per no buidar GitHub Pages" >&2
    fi
  fi
  git add -A data/
  if git diff --cached --quiet; then
    echo "Sense canvis, no cal commit."
  else
        git commit -m "Actualitza echo tops $(date -u +%Y-%m-%dT%H:%MZ)" -- data/
    git push
  fi
fi
