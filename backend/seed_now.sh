#!/bin/bash
cd "$(dirname "$0")"
.venv/bin/python -c 'import bcrypt'
echo IMPORT:$?
.venv/bin/python src/print_hash.py
