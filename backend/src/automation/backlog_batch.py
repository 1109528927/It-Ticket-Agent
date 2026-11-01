"""定时/手动批跑：扫积压单 → RAG → 草稿；简单单可按配置自动发回复，高危只起草。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from automation.actor import get_automation_actor_id
from automation.config import BATCH_LIMIT, BATCH_STALE_HOURS, PER_TICKET_RETRIES
from automation.drafts import send_auto_reply, upsert_reply_draft
from automation.reply_gen import generate_reply_draft_for_ticket, looks_high_risk
from config.request import SyncSessionLocal
from model.ticket import Ticket
from utils.retry import call_with_retry

logger = logging.getLogger(__name__)


def _friendly_fail(exc: Exception) -> str:
    msg = str(exc).lower()
    name = type(exc).__name__
    if "no_key" in msg or "api" in msg and "key" in msg:
        return "生成失败：未配置大模型密钥，请联系管理员"
    if "timeout" in name.lower() or "timeout" in msg:
        return "生成失败：模型响应超时，可稍后重试"
    if "milvus" in msg or "connection" in msg:
        return "生成失败：知识库暂不可用，可稍后重试"
    return f"生成失败，可稍后重试（{name}）"


def _select_backlog_tickets(
    limit: int, *, categories: list[str] | None = None
) -> list[dict[str, Any]]:
    stale_before = datetime.now() - timedelta(hours=max(1, BATCH_STALE_HOURS))
    with SyncSessionLocal() as db:
        cond = or_(
            Ticket.status == "pending",
            (Ticket.status == "processing") & (Ticket.updated_at <= stale_before),
        )
        stmt = select(Ticket).where(cond)
        if categories:
            stmt = stmt.where(Ticket.category.in_(categories))
        stmt = stmt.order_by(Ticket.updated_at.asc(), Ticket.id.asc()).limit(limit)
        rows = list(db.execute(stmt).scalars().all())
        return [
            {
                "id": int(t.id),
                "category": t.category,
                "title": t.title,
                "description": t.description,
                "status": t.status,
            }
            for t in rows
        ]


def process_one_backlog_ticket(
    ticket: dict[str, Any],
    *,
    actor_id: int,
    skip_high_risk: bool = False,
    auto_send_simple: bool = False,
) -> dict[str, Any]:
    tid = int(ticket["id"])
    risk = looks_high_risk(f"{ticket['title']}\n{ticket['description']}")
    if risk and skip_high_risk:
        from automation.user_notice import ensure_high_risk_user_notice

        ensure_high_risk_user_notice(
            ticket_id=tid,
            title=ticket["title"],
            description=ticket["description"],
            actor_id=actor_id,
        )
        return {
            "ticket_id": tid,
            "action": "draft_reply_skip_risk",
            "success": True,
            "detail": "高危单已按策略跳过，未生成草稿；已告知员工等白班处理",
        }

    def _gen():
        return generate_reply_draft_for_ticket(
            ticket_id=tid,
            category=ticket["category"],
            title=ticket["title"],
            description=ticket["description"],
            status=ticket["status"],
        )

    pack = call_with_retry(
        _gen,
        retries=PER_TICKET_RETRIES,
        label=f"batch.ticket.{tid}",
    )
    content = pack["content"]

    # 高危：永远只起草，不自动发送（夜班留给白班）
    will_auto_send = bool(auto_send_simple) and not risk

    meta = {
        **(pack.get("meta") or {}),
        "batch": True,
        "high_risk_hint": risk,
        "auto_sent": will_auto_send,
        "note": (
            "检出高危语义：仅起草，等白班提出/确认；批跑不会改密改权、不会自动发回复。"
            if risk
            else (
                "简单单：已自动发送回复并留审计记录。"
                if will_auto_send
                else "批跑只写草稿，不自动发送回复。"
            )
        ),
    }
    upsert_reply_draft(
        ticket_id=tid,
        content=content,
        source="batch",
        meta=meta,
        actor_id=actor_id,
        event_detail=(
            "批跑：已生成带依据回复草稿"
            + ("（高危：仅起草，等白班）" if risk else "")
            + ("；并已自动发送" if will_auto_send else "")
        ),
    )

    if risk:
        from automation.user_notice import ensure_high_risk_user_notice

        ensure_high_risk_user_notice(
            ticket_id=tid,
            title=ticket["title"],
            description=ticket["description"],
            actor_id=actor_id,
        )

    if will_auto_send:
        send_auto_reply(ticket_id=tid, content=content, actor_id=actor_id)
        return {
            "ticket_id": tid,
            "action": "auto_reply",
            "success": True,
            "detail": f"简单单已自动发送回复（约 {len(content)} 字），已留执行记录",
        }

    return {
        "ticket_id": tid,
        "action": "draft_reply",
        "success": True,
        "detail": (
            f"已生成回复草稿（约 {len(content)} 字）"
            + ("；高危仅起草，等白班处理" if risk else "")
        ),
    }


def run_backlog_batch(*, limit: int | None = None) -> dict[str, Any]:
    from automation.settings_store import load_config_sync

    cfg = load_config_sync()
    actor_id = get_automation_actor_id()
    cats = cfg.get("backlog_categories") or []
    tickets = _select_backlog_tickets(
        limit or BATCH_LIMIT, categories=cats or None
    )
    skip_risk = bool(cfg.get("skip_high_risk"))
    auto_send = bool(cfg.get("auto_send_simple_reply"))
    results: list[dict[str, Any]] = []
    for t in tickets:
        try:
            results.append(
                process_one_backlog_ticket(
                    t,
                    actor_id=actor_id,
                    skip_high_risk=skip_risk,
                    auto_send_simple=auto_send,
                )
            )
        except Exception as e:
            logger.exception("batch ticket failed id=%s", t.get("id"))
            results.append(
                {
                    "ticket_id": int(t["id"]),
                    "action": "draft_reply",
                    "success": False,
                    "detail": _friendly_fail(e),
                }
            )
    ok = sum(1 for r in results if r.get("success"))
    return {
        "scanned": len(tickets),
        "ok": ok,
        "failed": len(results) - ok,
        "results": results,
    }
