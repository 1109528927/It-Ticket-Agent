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


def claim_pending_to_automation(
    *,
    ticket_id: int,
    actor_id: int,
    detail: str = "简单单专席认领：非高危积压，已挂专席账号并进入处理中（可一键执行发送）",
) -> bool:
    """pending 且无 assignee → processing + 自动化账号。已认领则 False（幂等）。"""
    with SyncSessionLocal() as db:
        ticket = db.get(Ticket, int(ticket_id))
        if ticket is None:
            raise ValueError("ticket_not_found")
        if ticket.status != "pending" or ticket.assignee_id is not None:
            return False
        now = datetime.now()
        ticket.assignee_id = int(actor_id)
        ticket.status = "processing"
        ticket.updated_at = now
        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=int(actor_id),
                event_type="claim",
                detail=(detail or "自动化认领")[:500],
            )
        )
        db.commit()
        return True


def send_auto_reply(
    *,
    ticket_id: int,
    content: str,
    actor_id: int,
    resolve: bool = False,
) -> None:
    """简单单自动发送：写 reply + auto_reply；resolve=True 时置 auto_resolved。
    不改密、不确认高危。"""
    content = (content or "").strip()
    if not content:
        raise ValueError("empty_reply")

    with SyncSessionLocal() as db:
        ticket = db.get(Ticket, int(ticket_id))
        if ticket is None:
            raise ValueError("ticket_not_found")
        # 幂等：已自动结案或已关闭不再发
        if ticket.status in {"auto_resolved", "resolved", "closed"}:
            return
        now = datetime.now()
        if ticket.assignee_id is None:
            ticket.assignee_id = int(actor_id)
        if resolve:
            ticket.status = "auto_resolved"
            ticket.escalate = 0
            audit = "自动化：高置信非高危，已自动发送并结案（auto_resolved）"
        else:
            if ticket.status == "pending":
                ticket.status = "processing"
            # 已发回复但未高置信结案：进入等反馈
            if ticket.status in {"processing", "need_manual", "pending"}:
                ticket.status = "waiting_feedback"
            audit = "自动化：判定为简单单，已自动发送回复（非高危；等反馈）"
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
                detail=audit,
            )
        )
        if resolve:
            db.add(
                TicketEvent(
                    ticket_id=int(ticket_id),
                    actor_id=int(actor_id),
                    event_type="status",
                    detail="自动化：processing/pending → auto_resolved",
                )
            )
        db.commit()


def mark_draft_awaiting_adopt(*, ticket_id: int, actor_id: int) -> None:
    """标记草稿待客服采用（事件，供列表/大盘）。"""
    with SyncSessionLocal() as db:
        db.add(
            TicketEvent(
                ticket_id=int(ticket_id),
                actor_id=int(actor_id),
                event_type="draft_ready",
                detail="非高危草稿已就绪，待客服一键执行发送",
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
