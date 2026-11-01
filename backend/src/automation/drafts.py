"""工单助手草稿落库（客服处理页可读取）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from config.request import SyncSessionLocal
from model.automation import TicketAssistantDraft
from model.ticket import Ticket, TicketEvent


def upsert_reply_draft(
    *,
    ticket_id: int,
    content: str,
    source: str,
    meta: dict[str, Any] | None = None,
    actor_id: int,
    event_detail: str | None = None,
) -> None:
    content = (content or "").strip()
    if not content:
        raise ValueError("empty_draft")

    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    with SyncSessionLocal() as db:
        row = db.execute(
            select(TicketAssistantDraft).where(
                TicketAssistantDraft.ticket_id == int(ticket_id)
            )
        ).scalar_one_or_none()
        now = datetime.now()
        if row is None:
            db.add(
                TicketAssistantDraft(
                    ticket_id=int(ticket_id),
                    draft_type="reply",
                    content=content,
                    meta_json=meta_json,
                    source=source,
                    updated_at=now,
                )
            )
        else:
            row.content = content
            row.meta_json = meta_json
            row.source = source
            row.draft_type = "reply"
            row.updated_at = now

        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=int(actor_id),
                event_type="agent_draft",
                detail=(event_detail or f"自动化写入回复草稿（source={source}）")[:500],
            )
        )
        db.commit()


def send_auto_reply(
    *,
    ticket_id: int,
    content: str,
    actor_id: int,
) -> None:
    """简单单自动发送：写 reply + auto_reply 审计；不改密、不确认高危、不结案。"""
    content = (content or "").strip()
    if not content:
        raise ValueError("empty_reply")

    with SyncSessionLocal() as db:
        ticket = db.get(Ticket, int(ticket_id))
        if ticket is None:
            raise ValueError("ticket_not_found")
        now = datetime.now()
        # 未认领的 pending：挂到自动化账号并进入处理中，方便白班看清「夜里已回过」
        if ticket.status == "pending" and ticket.assignee_id is None:
            ticket.assignee_id = int(actor_id)
            ticket.status = "processing"
        ticket.updated_at = now
        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=int(actor_id),
                event_type="reply",
                detail=content,
            )
        )
        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=int(actor_id),
                event_type="auto_reply",
                detail="自动化：判定为简单单，已自动发送回复（非高危；未结案）",
            )
        )
        db.commit()


def get_reply_draft(ticket_id: int) -> dict[str, Any] | None:
    with SyncSessionLocal() as db:
        row = db.execute(
            select(TicketAssistantDraft).where(
                TicketAssistantDraft.ticket_id == int(ticket_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        meta = {}
        if row.meta_json:
            try:
                meta = json.loads(row.meta_json)
            except json.JSONDecodeError:
                meta = {}
        return {
            "ticket_id": row.ticket_id,
            "draft_type": row.draft_type,
            "content": row.content,
            "meta": meta,
            "source": row.source,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
