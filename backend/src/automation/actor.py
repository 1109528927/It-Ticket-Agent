"""自动化写事件时的系统操作者（必须是真实 user 行）。"""

from __future__ import annotations

from sqlalchemy import select

from automation.config import AUTOMATION_ACTOR_USER_ID
from config.request import SyncSessionLocal
from model.user import User

_cached_actor_id: int | None = None


def get_automation_actor_id() -> int:
    global _cached_actor_id
    if _cached_actor_id is not None:
        return _cached_actor_id

    if AUTOMATION_ACTOR_USER_ID:
        aid = int(AUTOMATION_ACTOR_USER_ID)
        with SyncSessionLocal() as db:
            row = db.execute(select(User.id).where(User.id == aid)).scalar_one_or_none()
            if row is None:
                raise RuntimeError(
                    f"AUTOMATION_ACTOR_USER_ID={aid} 在 user 表不存在，请改成真实客服 id"
                )
        _cached_actor_id = aid
        return aid

    with SyncSessionLocal() as db:
        row = db.execute(
            select(User.id).where(User.role == "support").order_by(User.id.asc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise RuntimeError("库中没有 support 用户，无法写自动化事件")
        _cached_actor_id = int(row)
        return _cached_actor_id
