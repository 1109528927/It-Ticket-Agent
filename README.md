# It-Ticket-Agent

内部 IT 智能工单台：员工提单、客服处理，LangGraph 双图 Agent，Milvus RAG。
按风险分流：低危可进简易台一键回复或按配置无人值守；高危只走人工确认（HITL）。

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
