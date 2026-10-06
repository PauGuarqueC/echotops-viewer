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
git -C "$HOME/radar-arxiu-javi" fetch --depth 1 origin main && git -C "$HOME/radar-arxiu-javi" reset --hard FETCH_HEAD || echo "nowcast: no s'ha pogut actualitzar l'arxiu" >&2
python3 scripts/nowcast_export.py --arrel "$HOME/radar-arxiu-javi/data" --sortida data/nowcast || echo "nowcast: error a l'exportació" >&2

git add data/
if git diff --cached --quiet; then
  echo "Sense canvis, no cal commit."
else
  git commit -m "Actualitza echo tops $(date -u +%Y-%m-%dT%H:%MZ)"
  git push
fi
