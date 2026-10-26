"""设备 / 网络类处理清单：勾选完才能标记解决。"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from model.ticket import Ticket, TicketChecklist, TicketEvent

# 按类别固定模板（不一次塞四类 Skill，只对本单类别种清单）
_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "device": [
        ("power", "已确认电源 / 能否开机"),
        ("cable", "已检查线缆、外设连接"),
        ("repro", "已复现或记录无法复现的现象"),
        ("kb_step", "已按知识库 / Skill 做过基础排查"),
        ("result", "已告知员工临时绕过或下一步"),
    ],
    "network": [
        ("link", "已确认网线 / Wi‑Fi / VPN 连接状态"),
        ("dns", "已检查 DNS / 网关或换网络试过"),
        ("scope", "已确认是单机还是多人问题"),
        ("kb_step", "已按知识库 / Skill 做过基础排查"),
        ("result", "已告知员工临时绕过或下一步"),
    ],
}

CHECKLIST_CATEGORIES = frozenset(_TEMPLATES.keys())


def _row_to_dict(row: TicketChecklist) -> dict:
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "item_key": row.item_key,
        "label": row.label,
        "checked": bool(row.checked),
        "updated_at": row.updated_at,
    }


async def ensure_checklist_for_ticket(db: AsyncSession, ticket: Ticket) -> list[dict]:
    """设备/网络单：没有清单则按模板插入；其它类别返回空列表。"""
    if ticket.category not in CHECKLIST_CATEGORIES:
        return []

    existing = (
        await db.execute(
            select(TicketChecklist)
            .where(TicketChecklist.ticket_id == ticket.id)
            .order_by(TicketChecklist.id.asc())
        )
    ).scalars().all()
    if existing:
        return [_row_to_dict(r) for r in existing]

    for key, label in _TEMPLATES[ticket.category]:
        db.add(
            TicketChecklist(
                ticket_id=ticket.id,
                item_key=key,
                label=label,
                checked=0,
            )
        )
    await db.flush()
    rows = (
        await db.execute(
            select(TicketChecklist)
            .where(TicketChecklist.ticket_id == ticket.id)
            .order_by(TicketChecklist.id.asc())
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def list_checklist(db: AsyncSession, ticket_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(TicketChecklist)
            .where(TicketChecklist.ticket_id == ticket_id)
            .order_by(TicketChecklist.id.asc())
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def set_checklist_item(
    db: AsyncSession,
    *,
    ticket_id: int,
    item_id: int,
    checked: bool,
    support_id: int,
) -> tuple[str, list[dict] | None]:
    """客服勾选 / 取消勾选。"""
    ticket = (
        await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ).scalar_one_or_none()
    if ticket is None:
        return "not_found", None
    if ticket.category not in CHECKLIST_CATEGORIES:
        return "not_applicable", None

    row = (
        await db.execute(
            select(TicketChecklist).where(
                TicketChecklist.id == item_id,
                TicketChecklist.ticket_id == ticket_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return "item_not_found", None

    now = datetime.now()
    await db.execute(
        update(TicketChecklist)
        .where(TicketChecklist.id == item_id, TicketChecklist.ticket_id == ticket_id)
        .values(checked=1 if checked else 0, updated_at=now)
    )
    ticket.updated_at = now
    db.add(
        TicketEvent(
            ticket_id=ticket_id,
            actor_id=support_id,
            event_type="checklist",
            detail=f"{'勾选' if checked else '取消'}：{row.label}",
        )
    )
    await db.flush()
    return "ok", await list_checklist(db, ticket_id)


async def checklist_all_done(db: AsyncSession, ticket_id: int, category: str) -> bool:
    """非设备/网络视为不需要清单。"""
    if category not in CHECKLIST_CATEGORIES:
        return True
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(TicketChecklist).where(
                    TicketChecklist.ticket_id == ticket_id
                )
            )
        ).scalar_one()
    )
    if total == 0:
        return False
    done = int(
        (
            await db.execute(
                select(func.count()).select_from(TicketChecklist).where(
                    TicketChecklist.ticket_id == ticket_id,
                    TicketChecklist.checked == 1,
                )
            )
        ).scalar_one()
    )
    return done == total
