"""给提单员工看的系统说明（时间线事件）。"""

from __future__ import annotations

from sqlalchemy import select

from automation.actor import get_automation_actor_id
from automation.reply_gen import build_high_risk_user_notice, looks_high_risk
from config.request import SyncSessionLocal
from model.ticket import TicketEvent


def _has_risk_notice(db, ticket_id: int) -> bool:
    row = db.execute(
        select(TicketEvent.id)
        .where(
            TicketEvent.ticket_id == int(ticket_id),
            TicketEvent.event_type == "risk_notice",
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def ensure_high_risk_user_notice(
    *,
    ticket_id: int,
    title: str,
    description: str,
    actor_id: int | None = None,
) -> bool:
    """若判定高危且尚未写过说明，写入 risk_notice。返回是否写入。"""
    blob = f"{title}\n{description}"
    if not looks_high_risk(blob):
        return False
    aid = int(actor_id) if actor_id is not None else get_automation_actor_id()
    detail = build_high_risk_user_notice(blob)
    with SyncSessionLocal() as db:
        if _has_risk_notice(db, ticket_id):
            return False
        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=aid,
                event_type="risk_notice",
                detail=detail[:2000],
            )
        )
        db.commit()
    return True
