"""只读工单工具（同步 Session，毫秒级）。列表极简，详情事件限 5 条。"""

from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import select

from config.request import SyncSessionLocal
from model.ticket import Ticket, TicketEvent

_LIST_LIMIT = 20
_DESC_LIMIT = 200
_EVENT_LIMIT = 5


@tool
def list_tickets(
    status: str | None = None,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """列出工单短列表。只返回 id、title、status，绝不返回描述。

    Args:
        status: 可选，按状态过滤。

    Returns:
        多行：#id | title | status
    """
    role = (state or {}).get("role") or ""
    user_id = int((state or {}).get("user_id") or 0)
    with SyncSessionLocal() as db:
        stmt = select(Ticket.id, Ticket.title, Ticket.status)
        if role == "employee":
            stmt = stmt.where(Ticket.user_id == user_id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        stmt = stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(_LIST_LIMIT)
        rows = db.execute(stmt).all()

    if not rows:
        return "当前没有工单。"
    return "\n".join(f"#{r.id} | {r.title} | {r.status}" for r in rows)


@tool
def get_ticket(
    ticket_id: int,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """按工单号查详情：短描述 + 最近 5 条 event；有交接摘要会标出。

    Args:
        ticket_id: 工单编号。
    """
    role = (state or {}).get("role") or ""
    user_id = int((state or {}).get("user_id") or 0)
    with SyncSessionLocal() as db:
        stmt = select(Ticket).where(Ticket.id == ticket_id)
        if role == "employee":
            stmt = stmt.where(Ticket.user_id == user_id)
        ticket = db.execute(stmt).scalar_one_or_none()
        if ticket is None:
            if role == "employee":
                return f"无权查看或不存在工单 #{ticket_id}。"
            return f"工单 #{ticket_id} 不存在。"
        events = (
            db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket_id)
                .order_by(TicketEvent.create_at.desc(), TicketEvent.id.desc())
                .limit(_EVENT_LIMIT)
            )
            .scalars()
            .all()
        )
        handoff = db.execute(
            select(TicketEvent)
            .where(
                TicketEvent.ticket_id == ticket_id,
                TicketEvent.event_type == "handoff",
            )
            .order_by(TicketEvent.create_at.desc(), TicketEvent.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    desc = (ticket.description or "")[:_DESC_LIMIT]
    lines = [
        f"#{ticket.id} {ticket.title}",
        f"类别={ticket.category} 状态={ticket.status}",
        f"描述：{desc}",
    ]
    if handoff and handoff.detail:
        lines.append(f"交接摘要：{(handoff.detail or '')[:300]}")
    if events:
        lines.append("最近事件：")
        for ev in reversed(events):
            lines.append(f"- {ev.event_type}: {(ev.detail or '')[:80]}")
    return "\n".join(lines)


SAFE_TOOLS: list[Any] = [list_tickets, get_ticket]
