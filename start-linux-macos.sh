#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
command -v git >/dev/null 2>&1 || { echo 'Git não encontrado no PATH.' >&2; exit 1; }
if [ ! -f .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c "import streamlit, plotly, pandas" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
