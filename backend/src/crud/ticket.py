from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crud.ticket_action import count_pending_actions, list_actions_for_ticket
from model.ticket import Ticket, TicketEvent

# 列表只取短字段，描述和事件流不进列表
_LIST_COLUMNS = (
    Ticket.id,
    Ticket.title,
    Ticket.category,
    Ticket.status,
    Ticket.priority,
    Ticket.escalate,
    Ticket.updated_at,
)


def _ticket_to_list_item(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "escalate": int(getattr(ticket, "escalate", 0) or 0),
        "updated_at": ticket.updated_at,
    }


async def list_tickets_for_employee(
    db: AsyncSession,
    *,
    user_id: int,
    status: str | None = None,
    category: str | None = None,
) -> list[dict]:
    stmt = select(*_LIST_COLUMNS).where(Ticket.user_id == user_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if category:
        stmt = stmt.where(Ticket.category == category)
    stmt = stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def list_tickets_for_support(
    db: AsyncSession,
    *,
    support_id: int,
    scope: str | None = None,
    status: str | None = None,
    lane: str | None = None,
) -> list[dict]:
    """工单池：不按提单人 user_id 收窄。
    scope=unclaimed / mine / simple_desk；
    lane=rag_ready（高置信可直接回）/ need_review（需核对）/ tracking（等反馈跟踪）。
    """
    import json

    from model.automation import TicketAssistantDraft

    stmt = select(*_LIST_COLUMNS)
    if scope == "unclaimed":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif scope == "mine":
        stmt = stmt.where(Ticket.assignee_id == support_id)
    elif scope == "simple_desk":
        from automation.actor import get_simple_desk_actor_id

        desk_id = get_simple_desk_actor_id()
        stmt = stmt.where(Ticket.assignee_id == int(desk_id))
    if status:
        stmt = stmt.where(Ticket.status == status)
    stmt = stmt.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
    rows = (await db.execute(stmt)).mappings().all()
    items = [dict(row) for row in rows]
    if not items:
        return items

    # 与夜班自动结案默认门槛一致；配置可读失败则 0.8
    thr = 0.8
    try:
        from automation.settings_store import load_config_sync

        thr = float(load_config_sync().get("night_confidence_threshold") or 0.8)
    except Exception:
        thr = 0.8

    ids = [int(r["id"]) for r in items]
    draft_rows = (
        await db.execute(
            select(TicketAssistantDraft).where(TicketAssistantDraft.ticket_id.in_(ids))
        )
    ).scalars().all()
    draft_map = {int(d.ticket_id): d for d in draft_rows}
    for it in items:
        d = draft_map.get(int(it["id"]))
        meta: dict = {}
        if d and d.meta_json:
            try:
                meta = json.loads(d.meta_json) or {}
            except json.JSONDecodeError:
                meta = {}
        it["has_draft"] = d is not None
        risk_hint = bool(meta.get("high_risk_hint"))
        it["high_risk_hint"] = risk_hint
        awaiting = bool(meta.get("awaiting_adopt"))
        if (
            d is not None
            and it.get("status") == "processing"
            and not meta.get("auto_sent")
            and not risk_hint
        ):
            awaiting = True if meta.get("awaiting_adopt", True) else False
        it["awaiting_adopt"] = bool(awaiting)
        conf = None
        try:
            if meta.get("confidence") is not None:
                conf = float(meta.get("confidence"))
        except (TypeError, ValueError):
            conf = None
        it["draft_confidence"] = conf
        # RAG 高置信 + 非高危 + 待采用 → 可直接回，人工事后跟踪
        it["rag_ready"] = bool(
            awaiting and (not risk_hint) and conf is not None and conf >= thr
        )

    if lane == "rag_ready":
        items = [i for i in items if i.get("rag_ready")]
    elif lane == "need_review":
        items = [
            i
            for i in items
            if i.get("awaiting_adopt") and not i.get("rag_ready")
        ]
    elif lane == "tracking":
        items = [i for i in items if i.get("status") == "waiting_feedback"]
    return items


async def create_ticket_for_employee(
    db: AsyncSession,
    *,
    user_id: int,
    category: str,
    title: str,
    description: str,
    priority: str,
) -> dict:
    ticket = Ticket(
        user_id=user_id,
        category=category,
        title=title,
        description=description,
        priority=priority,
        status="pending",
        assignee_id=None,
    )
    db.add(ticket)
    await db.flush()

    event = TicketEvent(
        ticket_id=ticket.id,
        actor_id=user_id,
        event_type="create",
        detail="创建工单",
    )
    db.add(event)

    # 建单即时分流：关键词判风险（不强制再调 Agent）
    # 非高危 → 挂简单单专席 processing；高危 → 留 pending 等其他客服
    try:
        from automation.actor import get_simple_desk_actor_id
        from automation.reply_gen import build_high_risk_user_notice, looks_high_risk

        blob = f"{title}\n{description}"
        if looks_high_risk(blob):
            db.add(
                TicketEvent(
                    ticket_id=ticket.id,
                    actor_id=user_id,
                    event_type="risk_notice",
                    detail=build_high_risk_user_notice(blob)[:2000],
                )
            )
        else:
            desk_id = get_simple_desk_actor_id()
            ticket.assignee_id = int(desk_id)
            ticket.status = "processing"
            db.add(
                TicketEvent(
                    ticket_id=ticket.id,
                    actor_id=int(desk_id),
                    event_type="claim",
                    detail="建单即时分流：非高危已自动挂简单单专席（无需手点认领）",
                )
            )
    except Exception:
        pass

    await db.flush()
    await db.refresh(ticket)
    return _ticket_to_list_item(ticket)


async def _ticket_detail_payload(
    db: AsyncSession,
    ticket: Ticket,
    *,
    include_assistant_draft: bool = False,
) -> dict:
    from crud.checklist import ensure_checklist_for_ticket
    from model.user import User

    event_stmt = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id)
        .order_by(TicketEvent.create_at.asc(), TicketEvent.id.asc())
    )
    events = (await db.execute(event_stmt)).scalars().all()
    actions = await list_actions_for_ticket(db, ticket.id)
    checklist = await ensure_checklist_for_ticket(db, ticket)
    creator = (
        await db.execute(select(User).where(User.id == ticket.user_id))
    ).scalar_one_or_none()
    assistant_draft = None
    if include_assistant_draft:
        try:
            from crud.automation import get_ticket_draft

            assistant_draft = await get_ticket_draft(db, ticket.id)
        except Exception:
            assistant_draft = None

    return {
        "id": ticket.id,
        "title": ticket.title,
        "category": ticket.category,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "escalate": int(getattr(ticket, "escalate", 0) or 0),
        "user_id": ticket.user_id,
        "creator_username": creator.username if creator else None,
        "creator_employee_no": creator.employee_no if creator else None,
        "create_at": ticket.create_at,
        "updated_at": ticket.updated_at,
        "events": events,
        "actions": actions,
        "checklist": checklist,
        "assistant_draft": assistant_draft,
    }


async def get_ticket_detail_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> dict | None:
    """按工单 id + 当前用户查；查不到返回 None（路由转 404，不暴露别人的单是否存在）。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None
    return await _ticket_detail_payload(db, ticket, include_assistant_draft=False)


async def get_ticket_detail_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
) -> dict | None:
    """客服看任意工单详情，不按提单人 user_id 过滤。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None
    return await _ticket_detail_payload(db, ticket, include_assistant_draft=True)


async def add_reply_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
    content: str,
) -> dict | None:
    """客服回复：插 reply；processing/need_manual → waiting_feedback。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None

    now = datetime.now()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="reply",
            detail=content,
        )
    )
    if ticket.status in {"processing", "need_manual"}:
        from_status = ticket.status
        ticket.status = "waiting_feedback"
        if from_status == "need_manual":
            ticket.escalate = 0
        db.add(
            TicketEvent(
                ticket_id=ticket_id,
                actor_id=support_id,
                event_type="status",
                detail=f"{from_status} 到 waiting_feedback（已回复，等员工反馈）",
            )
        )
    ticket.updated_at = now
    await db.flush()
    return await get_ticket_detail_for_support(db, ticket_id=ticket_id)


async def one_click_execute_simple_ticket(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
) -> tuple[str, dict | None]:
    """简单单专席一键执行：采纳草稿并发送 → waiting_feedback。
    高危语义 / 待确认高危动作一律拒绝（最后确认仍走人审）。"""
    import json

    from crud.automation import get_ticket_draft
    from crud.ticket_action import count_pending_actions
    from model.automation import TicketAssistantDraft
    from automation.reply_gen import looks_high_risk

    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.status not in {"processing", "need_manual"}:
        return "bad_state", None

    pending_n = await count_pending_actions(db, ticket_id)
    if pending_n > 0:
        return "blocked_pending_action", None

    blob = f"{ticket.title}\n{ticket.description}"
    draft = await get_ticket_draft(db, ticket_id)
    content = ((draft or {}).get("content") or "").strip()
    meta = (draft or {}).get("meta") or {}
    if meta.get("high_risk_hint") or looks_high_risk(blob) or looks_high_risk(content):
        return "high_risk", None
    if not content:
        return "no_draft", None

    now = datetime.now()
    # 执行权落到当前点击的客服（专席本人或代班），便于审计
    if ticket.assignee_id is None:
        ticket.assignee_id = int(support_id)

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="draft_adopt",
            detail="简单单专席一键执行：已采纳草稿",
        )
    )
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="reply",
            detail=content,
        )
    )
    from_status = ticket.status
    ticket.status = "waiting_feedback"
    ticket.escalate = 0
    ticket.updated_at = now
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="one_click_execute",
            detail=f"{from_status} 到 waiting_feedback（一键执行发送，非高危）",
        )
    )

    row = await db.get(TicketAssistantDraft, int(ticket_id))
    if row is not None:
        m = {}
        if row.meta_json:
            try:
                m = json.loads(row.meta_json) or {}
            except json.JSONDecodeError:
                m = {}
        m["awaiting_adopt"] = False
        m["one_click_executed"] = True
        m["adopted_by"] = int(support_id)
        m["adopted_at"] = now.isoformat(timespec="seconds")
        row.meta_json = json.dumps(m, ensure_ascii=False)
        row.updated_at = now

    await db.flush()
    detail = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    return "ok", detail


async def adopt_assistant_draft_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
) -> tuple[str, dict | None]:
    """记录一键采纳事件（大盘用）；返回草稿内容给前端填入。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None

    from crud.automation import get_ticket_draft

    draft = await get_ticket_draft(db, ticket_id)
    content = (draft or {}).get("content") if draft else None
    if not content or not str(content).strip():
        return "no_draft", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="draft_adopt",
            detail="客服一键采纳助手草稿（尚未发送）",
        )
    )
    # 清 awaiting 标记：改 meta
    try:
        from model.automation import TicketAssistantDraft
        import json

        row = await db.get(TicketAssistantDraft, int(ticket_id))
        if row is not None:
            meta = {}
            if row.meta_json:
                try:
                    meta = json.loads(row.meta_json)
                except json.JSONDecodeError:
                    meta = {}
            meta["awaiting_adopt"] = False
            meta["adopted_at"] = datetime.now().isoformat(timespec="seconds")
            meta["adopted_by"] = int(support_id)
            row.meta_json = json.dumps(meta, ensure_ascii=False)
            row.updated_at = datetime.now()
    except Exception:
        pass

    ticket.updated_at = datetime.now()
    await db.flush()
    detail = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    return "ok", {"content": str(content).strip(), "detail": detail}


async def add_comment_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
    detail: str,
) -> dict | None:
    """给自己的工单追加 comment；waiting_feedback 下捕获「好了/还不行」意图。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return None

    text = (detail or "").strip()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="comment",
            detail=text,
        )
    )
    now = datetime.now()
    if ticket.status == "waiting_feedback":
        intent = _feedback_intent(text)
        if intent == "resolved":
            ticket.status = "resolved"
            ticket.escalate = 0
            db.add(
                TicketEvent(
                    ticket_id=ticket_id,
                    actor_id=user_id,
                    event_type="status",
                    detail="waiting_feedback 到 resolved（员工反馈已解决）",
                )
            )
        elif intent == "escalate":
            ticket.status = "need_manual"
            ticket.escalate = 1
            db.add(
                TicketEvent(
                    ticket_id=ticket_id,
                    actor_id=user_id,
                    event_type="status",
                    detail="waiting_feedback 到 need_manual（员工反馈仍未解决，已升级）",
                )
            )
    ticket.updated_at = now
    await db.flush()
    return await get_ticket_detail_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user_id,
    )


def _feedback_intent(text: str) -> str | None:
    """粗粒度意图：好了 → resolved；还不行 → escalate。"""
    import re

    t = (text or "").strip().lower()
    if not t:
        return None
    if re.search(
        r"(还是不行|还不行|没好|未解决|仍然|依旧|不行|没解决|更糟)",
        t,
    ):
        return "escalate"
    if re.search(r"(好了|已解决|可以了|搞定|没问题了|ok了|谢谢.*好)", t):
        return "resolved"
    return None


async def close_ticket_for_employee(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> tuple[str, dict | None]:
    """员工撤销未认领工单：pending -> closed，记 close 事件。不删库。

    返回 (结果码, 详情)：
    - ok：成功
    - not_found：不是自己的单或不存在
    - not_pending：已认领等，不允许撤
    """
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None
    if ticket.status != "pending":
        return "not_pending", None

    ticket.status = "closed"
    ticket.updated_at = datetime.now()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="close",
            detail="员工撤销未认领工单",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user_id,
    )
    return "ok", detail


async def claim_ticket_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
) -> tuple[str, dict | None]:
    """客服认领：pending 变成 processing，写 assignee_id，记 claim 事件。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None
    if ticket.status != "pending" or ticket.assignee_id is not None:
        return "not_claimable", None

    ticket.status = "processing"
    ticket.assignee_id = support_id
    ticket.updated_at = datetime.now()
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="claim",
            detail="客服认领工单",
        )
    )
    from crud.checklist import ensure_checklist_for_ticket

    await ensure_checklist_for_ticket(db, ticket)
    await db.flush()
    await db.refresh(ticket)
    return "ok", _ticket_to_list_item(ticket)


# 客服普通改状态允许的边（认领走 /claim；高风险走 /actions；
# waiting_feedback / auto_resolved / need_manual 主要由回复与自动化写入）
SUPPORT_STATUS_EDGES: dict[str, set[str]] = {
    "processing": {"resolved", "waiting_feedback"},
    "waiting_feedback": {"resolved", "need_manual", "processing"},
    "need_manual": {"processing", "resolved"},
    "auto_resolved": {"closed"},
    "resolved": {"closed"},
}


async def change_ticket_status_for_support(
    db: AsyncSession,
    *,
    ticket_id: int,
    support_id: int,
    to_status: str,
) -> tuple[str, dict | None]:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        return "not_found", None

    from_status = ticket.status
    allowed = SUPPORT_STATUS_EDGES.get(from_status, set())
    if to_status not in allowed:
        return "bad_edge", None

    now = datetime.now()

    # mark_resolved：pending 高风险拦截；设备/网络须清单全勾
    if to_status == "resolved":
        from crud.checklist import checklist_all_done, ensure_checklist_for_ticket

        pending_n = await count_pending_actions(db, ticket_id)
        if pending_n > 0:
            return "blocked_pending_action", None
        await ensure_checklist_for_ticket(db, ticket)
        if not await checklist_all_done(db, ticket_id, ticket.category):
            return "blocked_checklist", None
        if from_status not in {"processing", "waiting_feedback", "need_manual"}:
            return "bad_edge", None
        result = await db.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.status == from_status)
            .values(status="resolved", escalate=0, updated_at=now)
        )
        if result.rowcount != 1:
            return "bad_edge", None
    else:
        values: dict = {"status": to_status, "updated_at": now}
        # 客服从 need_manual 拉回处理中时清升级标；标 need_manual 时置 1
        if to_status == "need_manual":
            values["escalate"] = 1
        elif to_status == "processing" and from_status == "need_manual":
            values["escalate"] = 0
        result = await db.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.status == from_status)
            .values(**values)
        )
        if result.rowcount != 1:
            return "bad_edge", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="status",
            detail=f"{from_status} 到 {to_status}",
        )
    )
    await db.flush()
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
    return "ok", _ticket_to_list_item(ticket)


_EMPLOYEE_DONE_STATUSES = frozenset({"resolved", "auto_resolved", "waiting_feedback"})


async def employee_confirm_resolved(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
) -> tuple[str, dict | None]:
    """员工确认已解决：resolved / auto_resolved / waiting_feedback → closed。"""
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.status not in _EMPLOYEE_DONE_STATUSES:
        return "bad_state", None

    from_status = ticket.status
    now = datetime.now()
    result = await db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.status == from_status,
            Ticket.user_id == user_id,
        )
        .values(status="closed", escalate=0, updated_at=now)
    )
    if result.rowcount != 1:
        return "bad_state", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="employee_confirm",
            detail=f"员工确认问题已解决，工单关闭（来自 {from_status}）",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db, ticket_id=ticket_id, user_id=user_id
    )
    return "ok", detail


async def employee_reopen_unresolved(
    db: AsyncSession,
    *,
    ticket_id: int,
    user_id: int,
    reason: str,
) -> tuple[str, dict | None]:
    """员工仍未解决：resolved→processing；auto_resolved/waiting_feedback→need_manual+escalate。"""
    reason = (reason or "").strip()
    if not reason:
        return "bad_reason", None

    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user_id)
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.status not in _EMPLOYEE_DONE_STATUSES:
        return "bad_state", None

    from_status = ticket.status
    # 夜班自动结案 / 等反馈：升级人工；普通 resolved 仍回处理中（兼容旧行为）
    if from_status in {"auto_resolved", "waiting_feedback"}:
        to_status = "need_manual"
        escalate = 1
    else:
        to_status = "processing"
        escalate = 0
    now = datetime.now()
    result = await db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.status == from_status,
            Ticket.user_id == user_id,
        )
        .values(status=to_status, escalate=escalate, updated_at=now)
    )
    if result.rowcount != 1:
        return "bad_state", None

    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=user_id,
            event_type="employee_reopen",
            detail=f"员工反馈仍未解决：{reason}（{from_status}→{to_status}）",
        )
    )
    await db.flush()
    detail = await get_ticket_detail_for_employee(
        db, ticket_id=ticket_id, user_id=user_id
    )
    return "ok", detail
