# It-Ticket-Agent

内部 IT 智能工单台：员工/客服双角色，LangGraph 双图 Agent，Milvus RAG，高危操作人机确认。

技术栈：Vue3 + FastAPI + PostgreSQL + LangGraph + Milvus

## 目录

```text
worker/
├── backend/          # FastAPI + Agent
│   ├── src/          # 业务与 agent 代码
│   ├── kb_source/    # 知识库 Markdown 数据源（见该目录 README）
│   ├── sql/          # 建表脚本
│   └── .env.example
├── front/            # Vue3 + Vite 前端
└── README.md
```

## 本地启动（简要）

### 后端

```bash
cd backend
cp .env.example .env   # 填写数据库与模型密钥
# 创建 venv 并安装 requirements.txt 后：
export PYTHONPATH=src
uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd front
pnpm install
pnpm run dev
```

## 说明

- 请勿提交 `.env`、`pwd.txt`、虚拟环境与 `node_modules`
- 知识库原文在 `backend/kb_source/`，Skill 短 SOP 在 `backend/src/agent/skills/`
