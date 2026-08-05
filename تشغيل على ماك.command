#!/usr/bin/env bash
# تشغيل البرنامج مباشرةً على ماك من المصدر (بلا بناء) — انقر مزدوجاً.
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (first run)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
echo "Starting HajjApp..."
python -m hajj_app
