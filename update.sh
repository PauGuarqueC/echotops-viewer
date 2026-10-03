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

git add data/
if git diff --cached --quiet; then
  echo "Sense canvis, no cal commit."
else
  git commit -m "Actualitza echo tops $(date -u +%Y-%m-%dT%H:%MZ)"
  git push
fi
