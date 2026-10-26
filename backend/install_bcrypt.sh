#!/bin/bash
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
uv pip install bcrypt --python .venv/bin/python
.venv/bin/python src/print_hash.py > support.hash
echo HASH_OK
