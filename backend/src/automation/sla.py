"""SLA 催办：超时未认领、待确认过久。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from automation.actor import get_automation_actor_id
from automation.config import SLA_CONFIRM_HOURS, SLA_UNCLAIMED_HOURS
from config.request import SyncSessionLocal
from model.ticket import Ticket, TicketEvent

logger = logging.getLogger(__name__)


def _already_nudged(db, ticket_id: int, event_type: str, since: datetime) -> bool:
    row = db.execute(
        select(TicketEvent.id)
        .where(
            TicketEvent.ticket_id == ticket_id,
            TicketEvent.event_type == event_type,
            TicketEvent.create_at >= since,
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def run_sla_sweep() -> dict[str, Any]:
    actor_id = get_automation_actor_id()
    now = datetime.now()
    unclaimed_before = now - timedelta(hours=max(1, SLA_UNCLAIMED_HOURS))
    confirm_before = now - timedelta(hours=max(1, SLA_CONFIRM_HOURS))
    # 同一类催办 12 小时内不重复刷事件
    dedupe_since = now - timedelta(hours=12)

    results: list[dict[str, Any]] = []

    with SyncSessionLocal() as db:
        # 1) 未认领超时
        pending_rows = list(
            db.execute(
                select(Ticket).where(
                    Ticket.status == "pending",
                    Ticket.assignee_id.is_(None),
                    Ticket.create_at <= unclaimed_before,
                )
            )
            .scalars()
            .all()
        )
        for t in pending_rows:
            if _already_nudged(db, t.id, "sla_unclaimed", dedupe_since):
                results.append(
                    {
                        "ticket_id": t.id,
                        "action": "sla_unclaimed_skip",
                        "success": True,
                        "detail": "近期已催办过，本次跳过",
                    }
                )
                continue
            old_pri = t.priority
            # low → medium，其它保持；只作提醒升级
            if t.priority == "low":
                db.execute(
                    update(Ticket)
                    .where(Ticket.id == t.id)
                    .values(priority="medium", updated_at=now)
                )
            db.add(
                TicketEvent(
                    ticket_id=t.id,
                    actor_id=actor_id,
                    event_type="sla_unclaimed",
                    detail=(
                        f"超过 {SLA_UNCLAIMED_HOURS} 小时未认领；"
                        f"优先级由「{old_pri}」"
                        + ("调整为「中」" if old_pri == "low" else "保持不变")
                    ),
                )
            )
            results.append(
                {
                    "ticket_id": t.id,
                    "action": "sla_unclaimed",
                    "success": True,
                    "detail": (
                        "已催办未认领"
                        + ("，优先级已调为中" if old_pri == "low" else "")
                    ),
                }
            )

        # 2) 待确认超时
        confirm_rows = list(
            db.execute(
                select(Ticket).where(
                    Ticket.status == "pending_confirm",
                    Ticket.updated_at <= confirm_before,
                )
            )
            .scalars()
            .all()
        )
        for t in confirm_rows:
            if _already_nudged(db, t.id, "sla_confirm_timeout", dedupe_since):
                results.append(
                    {
                        "ticket_id": t.id,
                        "action": "sla_confirm_skip",
                        "success": True,
                        "detail": "近期已催办过，本次跳过",
                    }
                )
                continue
            db.add(
                TicketEvent(
                    ticket_id=t.id,
                    actor_id=actor_id,
                    event_type="sla_confirm_timeout",
                    detail=(
                        f"高危待确认超过 {SLA_CONFIRM_HOURS} 小时，请客服尽快确认或拒绝；"
                        "自动化不会代为确认。"
                    ),
                )
            )
            results.append(
                {
                    "ticket_id": t.id,
                    "action": "sla_confirm_timeout",
                    "success": True,
                    "detail": "已催办：待确认超时，需人工确认或拒绝",
                }
            )

        db.commit()

    ok = sum(1 for r in results if r.get("success"))
    return {
        "scanned": len(results),
        "ok": ok,
        "failed": len(results) - ok,
        "results": results,
    }
