"""高风险执行器（第二版）：确认后真改本库用户，不再 audit_only 空转。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from model.ticket import Ticket
from model.user import User, UserToken
from utils.security import hash_password


async def _ticket_and_user(
    db: AsyncSession,
    *,
    ticket_id: int,
    payload: dict | None,
) -> tuple[Ticket | None, User | None, str]:
    """按工号优先，找不到则用工单提单人。"""
    ticket = (
        await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    if ticket is None:
        return None, None, "工单不存在"

    target_no = str((payload or {}).get("target_employee_no") or "").strip()
    user = None
    if target_no:
        user = (
            await db.execute(select(User).where(User.employee_no == target_no))
        ).scalar_one_or_none()
        if user is None:
            return ticket, None, f"工号 {target_no} 不存在"
    if user is None:
        user = (
            await db.execute(select(User).where(User.id == ticket.user_id))
        ).scalar_one_or_none()
    if user is None:
        return ticket, None, "找不到要对齐的用户"
    return ticket, user, ""


async def execute_reset_password(
    db: AsyncSession,
    *,
    ticket_id: int,
    payload: dict | None,
    new_password: str,
) -> dict:
    """写入 user.password，并清掉该用户 token。明文密码不进返回体。"""
    new_password = (new_password or "").strip()
    if len(new_password) < 6 or len(new_password) > 64:
        return {
            "execution": "failed",
            "message": "临时密码长度须为 6～64",
            "payload": {"target_employee_no": (payload or {}).get("target_employee_no")},
        }

    _ticket, user, err = await _ticket_and_user(
        db, ticket_id=ticket_id, payload=payload
    )
    if err or user is None:
        return {
            "execution": "failed",
            "message": err or "用户不存在",
            "payload": payload or {},
        }

    user.password = hash_password(new_password)
    await db.execute(delete(UserToken).where(UserToken.user_id == user.id))
    await db.flush()

    return {
        "execution": "applied",
        "message": f"已重置用户 {user.username}（工号 {user.employee_no}）的登录密码，旧会话已失效",
        "payload": {
            "target_employee_no": user.employee_no,
            "user_id": user.id,
            "username": user.username,
        },
    }


async def execute_change_permission(
    db: AsyncSession,
    *,
    ticket_id: int,
    payload: dict | None,
) -> dict:
    """写入 user.permission_group。"""
    group = str((payload or {}).get("group_name") or "").strip()
    if not group:
        return {
            "execution": "failed",
            "message": "缺少权限组名 group_name",
            "payload": payload or {},
        }

    ticket = (
        await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    if ticket is None:
        return {"execution": "failed", "message": "工单不存在", "payload": payload or {}}

    user = (
        await db.execute(select(User).where(User.id == ticket.user_id))
    ).scalar_one_or_none()
    if user is None:
        return {"execution": "failed", "message": "提单人不存在", "payload": payload or {}}

    user.permission_group = group
    await db.flush()

    return {
        "execution": "applied",
        "message": f"已将用户 {user.username}（工号 {user.employee_no}）权限组设为「{group}」",
        "payload": {
            "group_name": group,
            "user_id": user.id,
            "employee_no": user.employee_no,
        },
    }


async def run_executor(
    db: AsyncSession,
    action_type: str,
    *,
    ticket_id: int,
    payload: dict | None,
    new_password: str | None = None,
) -> dict:
    if action_type == "reset_password":
        return await execute_reset_password(
            db,
            ticket_id=ticket_id,
            payload=payload,
            new_password=new_password or "",
        )
    if action_type == "change_permission":
        return await execute_change_permission(
            db, ticket_id=ticket_id, payload=payload
        )
    return {
        "execution": "failed",
        "message": f"未知动作类型 {action_type}",
        "payload": payload or {},
    }
