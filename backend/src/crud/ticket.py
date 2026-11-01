from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crud.ticket_action import count_pending_actions, list_actions_for_ticket
from model.ticket import Ticket, TicketEvent

# 列表只取短字段，描述和事件流不进列表
_LIST_COLUMNS = (
    Ticket.id,
    Ticket.title,
    Ticket.category,
    Ticket.status,
    Ticket.priority,
    Ticket.updated_at,
)


def _ticket_to_list_item(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "updated_at": ticket.updated_at,
    }


async def list_tickets_for_employee(
    db: AsyncSession,
    *,
    user_id: int,
    status: str | None = None,
    category: str | None = None,
) -> list[dict]:
    stmt = select(*_LIST_COLUMNS).where(Ticket.user_id == user_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if category:
        stmt = stmt.where(Ticket.category == category)
    stmt = stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def list_tickets_for_support(
    db: AsyncSession,
    *,
    support_id: int,
    scope: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """工单池：不按提单人 user_id 收窄。scope=unclaimed 未认领，mine 当前客服认领的。"""
    stmt = select(*_LIST_COLUMNS)
    if scope == "unclaimed":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif scope == "mine":
        stmt = stmt.where(Ticket.assignee_id == support_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    stmt = stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def create_ticket_for_employee(
    db: AsyncSession,
    *,
    user_id: int,
    category: str,
    title: str,
    description: str,
    priority: str,
) -> dict:
    ticket = Ticket(
        user_id=user_id,
        category=category,
        title=title,
        description=description,
        priority=priority,
        status="pending",
        assignee_id=None,
    )
    db.add(ticket)
    await db.flush()

    event = TicketEvent(
        ticket_id=ticket.id,
        actor_id=user_id,
        event_type="create",
        detail="创建工单",
    )
    db.add(event)

    # 高危：同步写一条给员工看的说明（创建接口立刻能提示，详情时间线也能看见）
    try:
        from automation.reply_gen import build_high_risk_user_notice, looks_high_risk

        blob = f"{title}\n{description}"
        if looks_high_risk(blob):
            db.add(
                TicketEvent(
                    ticket_id=ticket.id,
                    actor_id=user_id,
                    event_type="risk_notice",
                    detail=build_high_risk_user_notice(blob)[:2000],
                )
            )
    except Exception:
        pass

    await db.flush()
    await db.refresh(ticket)
    return _ticket_to_list_item(ticket)


async def _ticket_detail_payload(db: AsyncSession, ticket: Ticket) -> dict:
    from crud.checklist import ensure_checklist_for_ticket
    from model.user import User

    event_stmt = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id)
        .order_by(TicketEvent.create_at.asc(), TicketEvent.id.asc())
    )
    events = (await db.execute(event_stmt)).scalars().all()
    actions = await list_actions_for_ticket(db, ticket.id)
    checklist = await ensure_checklist_for_ticket(db, ticket)
    creator = (
        await db.execute(select(User).where(User.id == ticket.user_id))
    ).scalar_one_or_none()
    assistant_draft = None
    try:
        from crud.automation import get_ticket_draft

        assistant_draft = await get_ticket_draft(db, ticket.id)
    except Exception:
        assistant_draft = None

    return {
        "id": ticket.id,
        "title": ticket.title,
        "category": ticket.category,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "user_id": ticket.user_id,
        "creator_username": creator.username if creator else None,
        "creator_employee_no": creator.employee_no if creator else None,
        "create_at": ticket.create_at,
        "updated_at": ticket.updated_at,
        "events": events,
        "actions": actions,
        "checklist": checklist,
        "assistant_draft": assistant_draft,
    }


async def get_ticket_detail_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> dict | None:
    """按工单 id + 当前用户查；查不到返回 None（路由转 404，不暴露别人的单是否存在）。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None
    return await _ticket_detail_payload(db, ticket)


async def get_ticket_detail_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
) -> dict | None:
    """客服看任意工单详情，不按提单人 user_id 过滤。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None
    return await _ticket_detail_payload(db, ticket)


async def add_reply_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
    content: str,
) -> dict | None:
    """客服回复：插 reply 事件，不改工单状态。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="reply",
            detail=content,
        )
    )
    ticket.updated_at = datetime.now()
    await db.flush()
    return await get_ticket_detail_for_support(db, ticket_id=ticket_id)


async def add_comment_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
    detail: str,
) -> dict | None:
    """给自己的工单追加一条 comment 事件；不改工单状态。别人的单返回 None。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="comment",
            detail=detail,
        )
    )
    ticket.updated_at = datetime.now()
    await db.flush()
    return await get_ticket_detail_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user_id,
    )


async def close_ticket_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> tuple[str, dict | None]:
    """员工撤销未认领工单：pending -> closed，记 close 事件。不删库。

    返回 (结果码, 详情)：
    - ok：成功
    - not_found：不是自己的单或不存在
    - not_pending：已认领等，不允许撤
    """
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None
    if ticket.status != "pending":
        return "not_pending", None

    ticket.status = "closed"
    ticket.updated_at = datetime.now()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="close",
            detail="员工撤销未认领工单",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user_id,
    )
    return "ok", detail


async def claim_ticket_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
) -> tuple[str, dict | None]:
    """客服认领：pending 变成 processing，写 assignee_id，记 claim 事件。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None
    if ticket.status != "pending" or ticket.assignee_id is not None:
        return "not_claimable", None

    ticket.status = "processing"
    ticket.assignee_id = support_id
    ticket.updated_at = datetime.now()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="claim",
            detail="客服认领工单",
        )
    )
    from crud.checklist import ensure_checklist_for_ticket

    await ensure_checklist_for_ticket(db, ticket)
    await db.flush()
    await db.refresh(ticket)
    return "ok", _ticket_to_list_item(ticket)


# 客服普通改状态允许的边（认领走 /claim；高风险走 /actions）
SUPPORT_STATUS_EDGES: dict[str, set[str]] = {
    "processing": {"resolved"},
    "resolved": {"closed"},
}


async def change_ticket_status_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
    to_status: str,
) -> tuple[str, dict | None]:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None

    from_status = ticket.status
    allowed = SUPPORT_STATUS_EDGES.get(from_status, set())
    if to_status not in allowed:
        return "bad_edge", None

    now = datetime.now()

    # mark_resolved：pending 高风险拦截；设备/网络须清单全勾
    if to_status == "resolved":
        from crud.checklist import checklist_all_done, ensure_checklist_for_ticket

        pending_n = await count_pending_actions(db, ticket_id)
        if pending_n > 0:
            return "blocked_pending_action", None
        await ensure_checklist_for_ticket(db, ticket)
        if not await checklist_all_done(db, ticket_id, ticket.category):
            return "blocked_checklist", None
        result = await db.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.status == "processing")
            .values(status="resolved", updated_at=now)
        )
        if result.rowcount != 1:
            return "bad_edge", None
    else:
        result = await db.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.status == from_status)
            .values(status=to_status, updated_at=now)
        )
        if result.rowcount != 1:
            return "bad_edge", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="status",
            detail=f"{from_status} 到 {to_status}",
        )
    )
    await db.flush()
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
    return "ok", _ticket_to_list_item(ticket)


async def employee_confirm_resolved(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> tuple[str, dict | None]:
    """员工确认已解决：resolved → closed。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.status != "resolved":
        return "bad_state", None

    now = datetime.now()
    result = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "resolved", Ticket.user_id == user_id)
        .values(status="closed", updated_at=now)
    )
    if result.rowcount != 1:
        return "bad_state", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="employee_confirm",
            detail="员工确认问题已解决，工单关闭",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db, ticket_id=ticket_id, user_id=user_id
    )
    return "ok", detail


async def employee_reopen_unresolved(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
    reason: str,
) -> tuple[str, dict | None]:
    """员工仍未解决：resolved → processing，写 reopen 事件。"""
    reason = (reason or "").strip()
    if not reason:
        return "bad_reason", None

    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.status != "resolved":
        return "bad_state", None

    now = datetime.now()
    result = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "resolved", Ticket.user_id == user_id)
        .values(status="processing", updated_at=now)
    )
    if result.rowcount != 1:
        return "bad_state", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="employee_reopen",
            detail=f"员工反馈仍未解决：{reason}",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db, ticket_id=ticket_id, user_id=user_id
    )
    return "ok", detail
