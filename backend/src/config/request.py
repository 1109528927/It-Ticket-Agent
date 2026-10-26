import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

# 加载 backend/.env
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 百炼千问（Agent）；密钥只放 .env
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
LLM_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")

# 默认 PostgreSQL；也可用 MySQL（改 .env 即可）
db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:123456@127.0.0.1:5433/it_ticket",
)


def _to_sync_url(url: str) -> str:
    """异步驱动换成同步驱动，给 Agent 图用。"""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("mysql+aiomysql://"):
        return "mysql+pymysql://" + url.removeprefix("mysql+aiomysql://")
    return url


# ② 创建异步引擎（连库的总管道）
async_engine = create_async_engine(
    db_url,
    echo=True,
    pool_size=10,
    max_overflow=20,
)

# ③ 创建异步会话工厂（按配置生产 session）
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ④ 依赖项：获取数据库会话，注入到路由
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Agent 工具是同步函数，不能 await get_db()，用独立同步连接池（小池，限抢主库）
_sync_url = _to_sync_url(db_url)
sync_engine = create_engine(
    _sync_url,
    echo=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=0,
)
SyncSessionLocal = sessionmaker(bind=sync_engine)