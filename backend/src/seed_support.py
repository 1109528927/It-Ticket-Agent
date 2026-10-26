"""写入一个客服账号。已存在则跳过。账号 support，密码 support123。"""

import asyncio

from config.request import AsyncSessionLocal
from crud.user import add_user, get_user_by_username


async def main():
    async with AsyncSessionLocal() as db:
        exists = await get_user_by_username(db, "support")
        if exists:
            print("support already exists")
            return
        await add_user(
            db,
            username="support",
            password="support123",
            employee_no="S0001",
            role="support",
        )
        await db.commit()
        print("support created")


if __name__ == "__main__":
    asyncio.run(main())
