#!/usr/bin/env bash
# 在本机已安装的 PostgreSQL 上建库、建角色（需能 sudo）。
# 数据目录仍是系统默认；D 盘目录 /mnt/d/Tools/postgresql-data 留给以后 Docker 挂载。
set -euo pipefail

DB_NAME="${DB_NAME:-it_ticket}"
DB_USER="${DB_USER:-postgres}"
DB_PASS="${DB_PASS:-123456}"

echo "==> 确保角色可密码登录、库存在（会提示输入 sudo 密码）"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  -- 若用系统 postgres 用户，只改密码
  ALTER USER postgres PASSWORD '${DB_PASS}';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'alter postgres password: %', SQLERRM;
END
\$\$;

SELECT 'ok' WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres');
SQL

sudo -u postgres psql -v ON_ERROR_STOP=1 -c "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres createdb -O postgres "${DB_NAME}"

echo "==> 库 ${DB_NAME} 就绪。DATABASE_URL 示例："
echo "postgresql+asyncpg://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}"
echo "接着跑: cd backend && source .venv/bin/activate && export PYTHONPATH=src && python srcipts/create_tables.py"
