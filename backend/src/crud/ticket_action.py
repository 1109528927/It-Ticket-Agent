import json
import logging
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from model.ticket import Ticket, TicketAction, TicketEvent
from utils.action_executors import run_executor

logger = logging.getLogger(__name__)


def _payload_loads(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _action_to_dict(row: TicketAction) -> dict:
    exec_raw = row.execution_result
    exec_obj = None
    if exec_raw:
        try:
            parsed = json.loads(exec_raw)
            exec_obj = parsed if isinstance(parsed, dict) else {"message": exec_raw}
        except json.JSONDecodeError:
            exec_obj = {"message": exec_raw}
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "proposer_id": row.proposer_id,
        "action_type": row.action_type,
        "reason": row.reason,
        "payload": _payload_loads(row.payload),
        "status": row.status,
        "execution_status": row.execution_status,
        "execution_result": exec_obj,
        "create_at": row.create_at,
        "updated_at": row.updated_at,
    }


async def list_actions_for_ticket(db: AsyncSession, ticket_id: int) -> list[dict]:
    stmt = (
        select(TicketAction)
        .where(TicketAction.ticket_id == ticket_id)
        .order_by(TicketAction.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_action_to_dict(row) for row in rows]


async def count_pending_actions(db: AsyncSession, ticket_id: int) -> int:
    stmt = select(func.count()).select_from(TicketAction).where(
        TicketAction.ticket_id == ticket_id,
        TicketAction.status == "pending",
    )
    return int((await db.execute(stmt)).scalar_one())


async def propose_action_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
    action_type: str,
    reason: str,
    payload: dict | None,
) -> tuple[str, dict | None]:
    """提出高风险：条件更新 processing→pending_confirm，再插 action + propose event。"""
    from model.user import User

    ticket = (
        await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    if ticket is None:
        return "not_found", None

    # 重置密码：目标工号一律取提单人，不采信前端乱填
    if action_type == "reset_password":
        owner = (
            await db.execute(select(User).where(User.id == ticket.user_id))
        ).scalar_one_or_none()
        if owner is None or not (owner.employee_no or "").strip():
            return "bad_target", None
        payload = {"target_employee_no": owner.employee_no.strip()}

    now = datetime.now()
    result = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "processing")
        .values(status="pending_confirm", updated_at=now)
    )
    if result.rowcount != 1:
        logger.warning(
            "propose 冲突 ticket_id=%s actor=%s action_type=%s",
            ticket_id,
            support_id,
            action_type,
        )
        return "bad_state", None

    action = TicketAction(
        ticket_id=ticket_id,
        proposer_id=support_id,
        action_type=action_type,
        reason=reason,
        payload=json.dumps(payload or {}, ensure_ascii=False),
        status="pending",
    )
    db.add(action)
    await db.flush()

    snap = {
        "action_id": action.id,
        "action_type": action_type,
        "reason": reason,
        "payload": payload or {},
    }
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="propose",
            detail=json.dumps(snap, ensure_ascii=False),
        )
    )
    await db.flush()

    logger.info(
        "propose ok ticket_id=%s action_id=%s actor=%s action_type=%s",
        ticket_id,
        action.id,
        support_id,
        action_type,
    )

    from crud.ticket import get_ticket_detail_for_support

    detail = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    return "ok", detail


async def confirm_action_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    action_id: int,
    support_id: int,
    new_password: str | None = None,
) -> tuple[str, dict | None]:
    """确认：先执行器；失败则保持 pending；成功再 confirmed + 工单回 processing。"""
    stmt = select(TicketAction).where(
        TicketAction.id == action_id,
        TicketAction.ticket_id == ticket_id,
    )
    action = (await db.execute(stmt)).scalar_one_or_none()
    if not action:
        return "not_found", None
    if action.status != "pending":
        logger.warning(
            "confirm 非 pending ticket_id=%s action_id=%s status=%s",
            ticket_id,
            action_id,
            action.status,
        )
        return "bad_state", None

    ticket = (
        await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    if ticket is None or ticket.status != "pending_confirm":
        return "bad_state", None

    payload = _payload_loads(action.payload)
    if action.action_type == "reset_password" and not (new_password or "").strip():
        return "need_password", None

    exec_result = await run_executor(
        db,
        action.action_type,
        ticket_id=ticket_id,
        payload=payload,
        new_password=new_password,
    )
    if exec_result.get("execution") == "failed":
        logger.warning(
            "confirm 执行失败 ticket_id=%s action_id=%s msg=%s",
            ticket_id,
            action_id,
            exec_result.get("message"),
        )
        # 不改 action/ticket 状态，便于客服改参数重试
        return "exec_failed", {"message": exec_result.get("message") or "执行失败"}

    now = datetime.now()
    upd_action = await db.execute(
        update(TicketAction)
        .where(
            TicketAction.id == action_id,
            TicketAction.ticket_id == ticket_id,
            TicketAction.status == "pending",
        )
        .values(
            status="confirmed",
            execution_status=exec_result.get("execution", "applied"),
            execution_result=json.dumps(exec_result, ensure_ascii=False),
            updated_at=now,
        )
    )
    if upd_action.rowcount != 1:
        return "bad_state", None

    upd_ticket = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "pending_confirm")
        .values(status="processing", updated_at=now)
    )
    if upd_ticket.rowcount != 1:
        return "bad_state", None

    # 事件里的 payload 不含明文密码
    safe_payload = dict(payload or {})
    snap = {
        "action_id": action_id,
        "action_type": action.action_type,
        "reason": action.reason,
        "payload": safe_payload,
        "execution": exec_result,
    }
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="confirm",
            detail=json.dumps(snap, ensure_ascii=False),
        )
    )
    await db.flush()

    logger.info(
        "confirm ok ticket_id=%s action_id=%s actor=%s action_type=%s exec=%s",
        ticket_id,
        action_id,
        support_id,
        action.action_type,
        exec_result.get("execution"),
    )

    from crud.ticket import get_ticket_detail_for_support

    detail = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    return "ok", detail


async def reject_action_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    action_id: int,
    support_id: int,
    reason: str,
) -> tuple[str, dict | None]:
    """拒绝：不调执行器；写 reject event。"""
    stmt = select(TicketAction).where(
        TicketAction.id == action_id,
        TicketAction.ticket_id == ticket_id,
    )
    action = (await db.execute(stmt)).scalar_one_or_none()
    if not action:
        return "not_found", None
    if action.status != "pending":
        logger.warning(
            "reject 非 pending ticket_id=%s action_id=%s status=%s",
            ticket_id,
            action_id,
            action.status,
        )
        return "bad_state", None

    now = datetime.now()
    upd_action = await db.execute(
        update(TicketAction)
        .where(
            TicketAction.id == action_id,
            TicketAction.ticket_id == ticket_id,
            TicketAction.status == "pending",
        )
        .values(status="rejected", updated_at=now)
    )
    if upd_action.rowcount != 1:
        logger.warning(
            "reject 条件更新失败 ticket_id=%s action_id=%s actor=%s",
            ticket_id,
            action_id,
            support_id,
        )
        return "bad_state", None

    upd_ticket = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "pending_confirm")
        .values(status="processing", updated_at=now)
    )
    if upd_ticket.rowcount != 1:
        logger.warning(
            "reject 工单状态冲突 ticket_id=%s action_id=%s",
            ticket_id,
            action_id,
        )
        return "bad_state", None

    snap = {
        "action_id": action_id,
        "action_type": action.action_type,
        "reject_reason": reason,
        "propose_reason": action.reason,
        "payload": _payload_loads(action.payload) or {},
    }
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="reject",
            detail=json.dumps(snap, ensure_ascii=False),
        )
    )
    await db.flush()

    logger.info(
        "reject ok ticket_id=%s action_id=%s actor=%s action_type=%s",
        ticket_id,
        action_id,
        support_id,
        action.action_type,
    )

    from crud.ticket import get_ticket_detail_for_support

    detail = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    return "ok", detail
