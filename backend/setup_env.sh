#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

echo "== recreate venv with uv =="
rm -rf .venv
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv/bin/python

echo "== create tables =="
mysql -uroot -p123456 < sql/init_user.sql

echo "== seed support =="
cd src
PYTHONPATH=. ../.venv/bin/python seed_support.py

echo "== done =="
