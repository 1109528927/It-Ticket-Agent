"""按当前模型在 DATABASE_URL 指向的库里建表（PostgreSQL / MySQL 均可）。"""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=True)

# 导入全部模型，注册到 Base.metadata
import model.chat  # noqa: F401
import model.kb  # noqa: F401
import model.ticket  # noqa: F401
import model.user  # noqa: F401
from config.request import async_engine, db_url
from model.user import Base
import asyncio


async def main() -> None:
    print("DATABASE_URL =", db_url)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("create_all 完成")


if __name__ == "__main__":
    asyncio.run(main())
