# 后端（FastAPI + Agent）

详见仓库根目录 [README.md](../README.md)。

```bash
cd backend
cp .env.example .env
# 安装依赖后：
export PYTHONPATH=src
uvicorn main:app --reload --port 8000
```

Swagger：http://127.0.0.1:8000/docs  

知识库数据源：`kb_source/`（README 见该目录）。
