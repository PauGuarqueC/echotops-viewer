#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -f venv/bin/activate ]; then
  source venv/bin/activate
fi

python3 scripts/descarrega_echotops_sftp.py
python3 scripts/process_tiffs.py
python3 scripts/build_manifest.py

rsync -a ~/echotops-data/png/ data/png/

# --- Nowcasting: tempestes enganxades (compost AEMET) ---
python3 scripts/aemet_compo.py --sortida "$HOME/echotops-data/aemet" || echo "nowcast: no s'ha pogut descarregar el compost" >&2
python3 scripts/nowcast_export.py --arrel "$HOME/echotops-data/aemet" --sortida data/nowcast || echo "nowcast: error a l'exportació" >&2

git add data/
if git diff --cached --quiet; then
  echo "Sense canvis, no cal commit."
else
  git commit -m "Actualitza echo tops $(date -u +%Y-%m-%dT%H:%MZ)"
  git push
fi
