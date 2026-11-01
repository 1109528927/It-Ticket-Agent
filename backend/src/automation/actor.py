"""自动化 / 简单单专席操作者（必须是真实 support user 行）。"""

from __future__ import annotations

from sqlalchemy import select

from automation.config import AUTOMATION_ACTOR_USER_ID
from config.request import SyncSessionLocal
from model.user import User

_cached_actor_id: int | None = None

# 与 seed 客服同口令哈希（演示用）；专席用户名固定
_SIMPLE_DESK_USERNAME = "simple_desk"
_SIMPLE_DESK_EMPLOYEE_NO = "S-SIMPLE"
# 与 seed 客服相同的 bcrypt（明文 support123）
_SUPPORT_PWD_HASH = (
    "$2b$12$zjrpBSH6IFf5Lx0mOo3igO.7yGqYDqrpwA.lWzx/qqeJsZKMUjNrO"
)


def get_automation_actor_id() -> int:
    """简单单专席账号 id：环境变量 > simple_desk 用户 > 自动建专席 > 第一个 support。"""
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
            select(User.id)
            .where(User.username == _SIMPLE_DESK_USERNAME, User.role == "support")
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            _cached_actor_id = int(row)
            return _cached_actor_id

        # 自动建「简单单专席」
        exists_no = db.execute(
            select(User.id).where(User.employee_no == _SIMPLE_DESK_EMPLOYEE_NO)
        ).scalar_one_or_none()
        if exists_no is None:
            desk = User(
                username=_SIMPLE_DESK_USERNAME,
                password=_SUPPORT_PWD_HASH,
                employee_no=_SIMPLE_DESK_EMPLOYEE_NO,
                role="support",
            )
            db.add(desk)
            db.commit()
            db.refresh(desk)
            _cached_actor_id = int(desk.id)
            return _cached_actor_id

        row = db.execute(
            select(User.id).where(User.role == "support").order_by(User.id.asc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise RuntimeError("库中没有 support 用户，无法写自动化事件")
        _cached_actor_id = int(row)
        return _cached_actor_id


def get_simple_desk_actor_id() -> int:
    """别名：简单单专席 = 自动化 actor。"""
    return get_automation_actor_id()
