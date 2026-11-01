"""定时/手动批跑：扫积压单 → RAG → 草稿；非高危认领挂待采用；高置信可自动结案。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from automation.actor import get_automation_actor_id
from automation.config import BATCH_LIMIT, BATCH_STALE_HOURS, PER_TICKET_RETRIES
from automation.drafts import (
    claim_pending_to_automation,
    mark_draft_awaiting_adopt,
    send_auto_reply,
    upsert_reply_draft,
)
from automation.reply_gen import generate_reply_draft_for_ticket, looks_high_risk
from config.request import SyncSessionLocal
from model.automation import TicketAssistantDraft
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
    """只选：pending；或久未更新的 processing；已有终态/等反馈的不进批（幂等）。"""
    stale_before = datetime.now() - timedelta(hours=max(1, BATCH_STALE_HOURS))
    with SyncSessionLocal() as db:
        cond = or_(
            Ticket.status == "pending",
            (Ticket.status == "processing") & (Ticket.updated_at <= stale_before),
        )
        stmt = select(Ticket).where(cond)
        if categories:
            stmt = stmt.where(Ticket.category.in_(categories))
        stmt = stmt.order_by(Ticket.updated_at.asc(), Ticket.id.asc()).limit(limit * 3)
        rows = list(db.execute(stmt).scalars().all())
        out: list[dict[str, Any]] = []
        for t in rows:
            has_draft = (
                db.execute(
                    select(TicketAssistantDraft.ticket_id).where(
                        TicketAssistantDraft.ticket_id == int(t.id)
                    )
                ).scalar_one_or_none()
                is not None
            )
            # 幂等：已有草稿且已不在 pending → 本轮跳过（避免重复认领/重写）
            if has_draft and t.status != "pending":
                continue
            out.append(
                {
                    "id": int(t.id),
                    "category": t.category,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "has_draft": has_draft,
                }
            )
            if len(out) >= limit:
                break
        return out


def process_one_backlog_ticket(
    ticket: dict[str, Any],
    *,
    actor_id: int,
    skip_high_risk: bool = False,
    auto_send_simple: bool = False,
    enable_night_auto_resolve: bool = False,
    night_confidence_threshold: float = 0.8,
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

    # pending 已有草稿：不重跑模型（幂等）
    if ticket.get("has_draft") and ticket.get("status") == "pending":
        if risk:
            from automation.user_notice import ensure_high_risk_user_notice

            ensure_high_risk_user_notice(
                ticket_id=tid,
                title=ticket["title"],
                description=ticket["description"],
                actor_id=actor_id,
            )
            return {
                "ticket_id": tid,
                "action": "draft_reply",
                "success": True,
                "detail": "高危已有草稿：保持待处理，等白班，不自动认领",
            }
        claimed = claim_pending_to_automation(ticket_id=tid, actor_id=actor_id)
        mark_draft_awaiting_adopt(ticket_id=tid, actor_id=actor_id)
        return {
            "ticket_id": tid,
            "action": "claim_await_adopt",
            "success": True,
            "detail": (
                "已有草稿：自动化认领并标待采用"
                if claimed
                else "已有草稿：此前已认领，标待采用"
            ),
        }

    try:
        pack = call_with_retry(
            lambda: generate_reply_draft_for_ticket(
                ticket_id=tid,
                category=ticket["category"],
                title=ticket["title"],
                description=ticket["description"],
                status=ticket["status"],
            ),
            retries=PER_TICKET_RETRIES,
            label=f"batch.ticket.{tid}",
        )
    except Exception as e:
        # JSON/模型异常：降级记失败，不崩整批
        logger.exception("batch generate failed id=%s", tid)
        return {
            "ticket_id": tid,
            "action": "draft_reply",
            "success": False,
            "detail": _friendly_fail(e),
        }

    content = (pack.get("content") or "").strip()
    base_meta = dict(pack.get("meta") or {})
    confidence = float(base_meta.get("confidence") or 0.0)
    parse_ok = bool(base_meta.get("parse_ok", True))
    if not content:
        return {
            "ticket_id": tid,
            "action": "draft_reply",
            "success": False,
            "detail": "生成失败：模型未返回可用草稿，已降级人工",
        }

    thr = float(night_confidence_threshold or 0.8)
    # 解析失败强制低置信，走人工待采用
    if not parse_ok:
        confidence = 0.0

    can_auto_resolve = (
        bool(enable_night_auto_resolve)
        and (not risk)
        and confidence >= thr
        and parse_ok
    )
    # 兼容旧开关：开自动回但不结案 → 发回复进 waiting_feedback
    will_auto_send = (bool(auto_send_simple) or can_auto_resolve) and (not risk)

    meta = {
        **base_meta,
        "batch": True,
        "high_risk_hint": risk,
        "confidence": confidence,
        "awaiting_adopt": (not risk) and (not will_auto_send),
        "auto_sent": will_auto_send,
        "auto_resolved": can_auto_resolve,
        "note": (
            "检出高危语义：仅起草，等白班提出/确认；批跑不会改密改权、不会自动发回复。"
            if risk
            else (
                "高置信非高危：已自动发送并 auto_resolved。"
                if can_auto_resolve
                else (
                    "简单单：已自动发送，进入等反馈。"
                    if will_auto_send
                    else "非高危：已认领并写草稿，待客服一键采用后发送。"
                )
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
            + (f"（confidence={confidence:.2f}）")
            + ("；高危：仅起草，等白班" if risk else "")
            + ("；已自动结案" if can_auto_resolve else "")
            + ("；已自动发送" if will_auto_send and not can_auto_resolve else "")
            + ("；待采用" if meta["awaiting_adopt"] else "")
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
        # 高危不进简单单专席：留 pending 给其他客服认领处理（提出+人审）
        return {
            "ticket_id": tid,
            "action": "draft_reply",
            "success": True,
            "detail": (
                f"高危仅起草（约 {len(content)} 字），留在未认领池供其他客服处理；"
                "不进简单单专席、不发送、不改密改权"
            ),
        }

    # 非高危：先挂自动化账号进 processing
    claim_pending_to_automation(ticket_id=tid, actor_id=actor_id)

    if will_auto_send:
        send_auto_reply(
            ticket_id=tid,
            content=content,
            actor_id=actor_id,
            resolve=can_auto_resolve,
        )
        return {
            "ticket_id": tid,
            "action": "auto_resolved" if can_auto_resolve else "auto_reply",
            "success": True,
            "detail": (
                f"高置信({confidence:.2f})已自动发送并结案"
                if can_auto_resolve
                else f"简单单已自动发送（confidence={confidence:.2f}），进入等反馈"
            ),
        }

    mark_draft_awaiting_adopt(ticket_id=tid, actor_id=actor_id)
    return {
        "ticket_id": tid,
        "action": "claim_await_adopt",
        "success": True,
        "detail": (
            f"已认领并写草稿待采用（约 {len(content)} 字，confidence={confidence:.2f}）"
            + ("；JSON 解析失败已降级人工" if not parse_ok else "")
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
    night_resolve = bool(cfg.get("enable_night_auto_resolve"))
    thr = float(cfg.get("night_confidence_threshold") or 0.8)
    results: list[dict[str, Any]] = []
    for t in tickets:
        try:
            results.append(
                process_one_backlog_ticket(
                    t,
                    actor_id=actor_id,
                    skip_high_risk=skip_risk,
                    auto_send_simple=auto_send,
                    enable_night_auto_resolve=night_resolve,
                    night_confidence_threshold=thr,
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
