"""白天副驾：认领后异步生成回复草稿（有草稿则跳过）。"""

from __future__ import annotations

import logging
import threading

from automation.drafts import get_reply_draft, mark_draft_awaiting_adopt, upsert_reply_draft
from automation.reply_gen import generate_reply_draft_for_ticket, looks_high_risk
from config.request import SyncSessionLocal
from model.ticket import Ticket

logger = logging.getLogger(__name__)


def schedule_draft_after_claim(ticket_id: int, *, actor_id: int) -> None:
    def _job() -> None:
        try:
            run_draft_after_claim(int(ticket_id), actor_id=int(actor_id))
        except Exception:
            logger.exception("copilot draft failed ticket_id=%s", ticket_id)

    threading.Thread(
        target=_job, name=f"copilot-draft-{ticket_id}", daemon=True
    ).start()


def run_draft_after_claim(ticket_id: int, *, actor_id: int) -> dict:
    existing = get_reply_draft(ticket_id)
    if existing and (existing.get("content") or "").strip():
        return {"skipped": True, "reason": "already_has_draft"}

    with SyncSessionLocal() as db:
        t = db.get(Ticket, int(ticket_id))
        if t is None:
            return {"skipped": True, "reason": "not_found"}
        category = t.category
        title = t.title
        description = t.description
        status = t.status

    risk = looks_high_risk(f"{title}\n{description}")
    pack = generate_reply_draft_for_ticket(
        ticket_id=int(ticket_id),
        category=category,
        title=title,
        description=description,
        status=status,
    )
    content = (pack.get("content") or "").strip()
    if not content:
        return {"skipped": True, "reason": "empty"}

    meta = {
        **(pack.get("meta") or {}),
        "source_hint": "claim_copilot",
        "awaiting_adopt": not risk,
        "high_risk_hint": risk,
    }
    upsert_reply_draft(
        ticket_id=int(ticket_id),
        content=content,
        source="claim",
        meta=meta,
        actor_id=int(actor_id),
        event_detail="认领后副驾：已生成回复草稿",
    )
    if not risk:
        mark_draft_awaiting_adopt(ticket_id=int(ticket_id), actor_id=int(actor_id))
    return {"ok": True, "len": len(content), "confidence": meta.get("confidence")}
