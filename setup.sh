#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

if [[ "${1:-}" == "--full" ]]; then
  python -m pip install -r requirements.txt
else
  python -m pip install -r requirements-quickstart.txt
fi

python qwen3_coder_quickstart.py --check

echo
echo "Qwen3-Coder preparado."
echo "Ative com: source .venv/bin/activate"
