#!/bin/bash
cd "$(dirname "$0")"
echo RAN > ran.txt
.venv/bin/python -c 'open("pytouch.txt","w").write("hi\n")'
echo TOUCH:$? >> ran.txt
.venv/bin/python src/_init_db.py
echo PY:$? >> ran.txt
ls -l init-result.txt >> ran.txt
