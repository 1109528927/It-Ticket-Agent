"""员工交接摘要：只写库，不调大模型。"""

from typing import Annotated, Any
from datetime import datetime

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import select

from config.request import SyncSessionLocal
from model.ticket import Ticket, TicketEvent


@tool
def write_handoff_summary(
    ticket_id: int,
    summary: str,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """把与客服的沟通结果写成交接摘要落库。客服接手时靠读库看到，不是两个 Agent 互相说话。

    Args:
        ticket_id: 工单编号（必须是自己的单）。
        summary: 交接摘要正文，说明现象、已做排查、还缺什么。

    Returns:
        成功或失败说明。
    """
    summary = (summary or "").strip()
    if not summary:
        return "缺少 summary，请写清交接内容。"
    user_id = int((state or {}).get("user_id") or 0)
    role = (state or {}).get("role") or ""
    if role != "employee":
        return "仅员工可写交接摘要。"

    with SyncSessionLocal() as db:
        ticket = db.execute(
            select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
        ).scalar_one_or_none()
        if ticket is None:
            return "无权或工单不存在：只能给自己的工单写交接摘要。"
        db.add(
            TicketEvent(
                ticket_id=ticket_id,
                actor_id=user_id,
                event_type="handoff",
                detail=summary[:2000],
            )
        )
        ticket.updated_at = datetime.now()
        db.commit()
    return "已写入交接摘要，客服可在工单详情中查看。"


HANDOFF_TOOLS: list[Any] = [write_handoff_summary]
