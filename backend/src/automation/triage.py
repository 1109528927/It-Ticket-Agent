"""建单后初审：建议类别/优先级 + 回复草稿（不改高危、默认不强制改库字段）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select

from automation.actor import get_automation_actor_id
from automation.config import PER_TICKET_RETRIES
from automation.drafts import (
    claim_pending_to_automation,
    mark_draft_awaiting_adopt,
    send_auto_reply,
    upsert_reply_draft,
)
from automation.reply_gen import generate_reply_draft_for_ticket, looks_high_risk
from automation.settings_store import load_config_sync
from config.request import DASHSCOPE_API_KEY, SyncSessionLocal
from llm.client import model
from model.ticket import Ticket, TicketEvent
from utils.retry import call_with_retry

logger = logging.getLogger(__name__)

_CATEGORIES = ("account", "device", "network", "permission")
_PRIORITIES = ("low", "medium", "high")


class TriageSuggestion(BaseModel):
    category: str = Field(description="account/device/network/permission")
    priority: str = Field(description="low/medium/high")
    reason: str = Field(description="一句话理由")


def _suggest_triage(title: str, description: str, category: str, priority: str) -> dict[str, Any]:
    if not DASHSCOPE_API_KEY:
        return {
            "category": category,
            "priority": priority,
            "reason": "未配置模型，保留原值",
            "applied": False,
        }

    bound = model.with_structured_output(TriageSuggestion)
    result = call_with_retry(
        bound.invoke,
        [
            SystemMessage(
                content=(
                    "根据内部 IT 工单标题与描述，建议类别与优先级。"
                    "类别只能是 account/device/network/permission；"
                    "优先级 low/medium/high。"
                    "请用 JSON 结构化输出（字段 category/priority/reason）。"
                )
            ),
            HumanMessage(
                content=f"当前类别={category} 优先级={priority}\n标题：{title}\n描述：{description}"
            ),
        ],
        retries=PER_TICKET_RETRIES,
        label="automation.triage_llm",
    )
    cat = (result.category or category).strip().lower()
    pri = (result.priority or priority).strip().lower()
    if cat not in _CATEGORIES:
        cat = category
    if pri not in _PRIORITIES:
        pri = priority
    return {
        "category": cat,
        "priority": pri,
        "reason": (result.reason or "").strip()[:200],
        "applied": False,
    }


def run_triage_for_ticket(ticket_id: int) -> dict[str, Any]:
    """同步执行；供建单后后台线程与手动重跑调用。"""
    actor_id = get_automation_actor_id()
    with SyncSessionLocal() as db:
        ticket = db.execute(
            select(Ticket).where(Ticket.id == int(ticket_id))
        ).scalar_one_or_none()
        if ticket is None:
            raise ValueError("not_found")
        title = ticket.title
        description = ticket.description
        category = ticket.category
        priority = ticket.priority
        status = ticket.status
        tid = ticket.id

    suggestion = _suggest_triage(title, description, category, priority)

    # 仅当建议与原值不同时，写入建议事件；不自动改 ticket 字段（客服可见后决定）
    with SyncSessionLocal() as db:
        db.add(
            TicketEvent(
                ticket_id=tid,
                actor_id=actor_id,
                event_type="auto_triage",
                detail=json.dumps(
                    {
                        "suggested_category": suggestion["category"],
                        "suggested_priority": suggestion["priority"],
                        "reason": suggestion["reason"],
                        "original_category": category,
                        "original_priority": priority,
                    },
                    ensure_ascii=False,
                )[:2000],
            )
        )
        db.commit()

    draft_pack = generate_reply_draft_for_ticket(
        ticket_id=tid,
        category=suggestion["category"] or category,
        title=title,
        description=description,
        status=status,
    )
    risk = looks_high_risk(f"{title}\n{description}")
    base_meta = dict(draft_pack.get("meta") or {})
    conf = float(base_meta.get("confidence") or 0.0)
    parse_ok = bool(base_meta.get("parse_ok", True))
    if not parse_ok:
        conf = 0.0

    cfg = load_config_sync()
    thr = float(cfg.get("night_confidence_threshold") or 0.8)
    auto_send = bool(cfg.get("auto_send_simple_reply"))
    night_resolve = bool(cfg.get("enable_night_auto_resolve"))
    can_auto_resolve = (
        night_resolve and (not risk) and conf >= thr and parse_ok
    )
    will_auto_send = (auto_send or can_auto_resolve) and (not risk)

    meta = {
        **base_meta,
        "triage": suggestion,
        "high_risk_hint": risk,
        "confidence": conf,
        "awaiting_adopt": (not risk) and (not will_auto_send),
        "auto_sent": will_auto_send,
        "auto_resolved": can_auto_resolve,
    }
    upsert_reply_draft(
        ticket_id=tid,
        content=draft_pack["content"],
        source="triage",
        meta=meta,
        actor_id=actor_id,
        event_detail=(
            "建单初审：已生成建议与回复草稿"
            + (
                "（高危：仅起草，已告知员工等人工处理）"
                if risk
                else (
                    "（非高危：已按开关自动发送"
                    + ("并结案）" if can_auto_resolve else "，进入等反馈）")
                    if will_auto_send
                    else "（非高危：专席可核对/一键执行）"
                )
            )
        ),
    )
    if risk:
        from automation.user_notice import ensure_high_risk_user_notice

        ensure_high_risk_user_notice(
            ticket_id=tid,
            title=title,
            description=description,
            actor_id=actor_id,
        )
    else:
        # 建单时若未挂上专席（异常兜底），初审再认领一次
        claim_pending_to_automation(
            ticket_id=tid,
            actor_id=actor_id,
            detail="建单初审兜底：非高危挂简单单专席",
        )
        if will_auto_send:
            send_auto_reply(
                ticket_id=tid,
                content=draft_pack["content"],
                actor_id=actor_id,
                resolve=can_auto_resolve,
            )
        else:
            mark_draft_awaiting_adopt(ticket_id=tid, actor_id=actor_id)
    return {"ticket_id": tid, "triage": suggestion, "draft_len": len(draft_pack["content"])}


def schedule_triage_after_create(ticket_id: int) -> None:
    """不阻塞 HTTP：后台线程跑初审。开关读 automation_config。"""
    cfg = load_config_sync()
    if not cfg.get("enable_triage_on_create", True):
        return

    import threading

    def _job():
        try:
            run_triage_for_ticket(int(ticket_id))
            logger.info("triage ok ticket_id=%s", ticket_id)
        except Exception:
            logger.exception("triage failed ticket_id=%s", ticket_id)

    threading.Thread(target=_job, name=f"triage-{ticket_id}", daemon=True).start()
