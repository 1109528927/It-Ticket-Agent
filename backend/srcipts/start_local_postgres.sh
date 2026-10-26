#!/usr/bin/env bash
# 启动 D 盘便携 PostgreSQL（端口 5433，密码 123456）
set -euo pipefail
PG_HOME=/mnt/d/Tools/pgsql
DATA="${HOME}/.local/share/worker-ai-pgdata"

if [ ! -d "$DATA" ]; then
  echo "数据目录不存在: $DATA"
  exit 1
fi

if "$PG_HOME/bin/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
  echo "已在运行 127.0.0.1:5433"
  exit 0
fi

"$PG_HOME/bin/pg_ctl" -D "$DATA" -l "$DATA/pg.log" start
echo "已启动 127.0.0.1:5433  db=it_ticket  user=postgres  password=123456"
