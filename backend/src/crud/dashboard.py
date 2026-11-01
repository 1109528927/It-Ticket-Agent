"""大盘纯 SQL 聚合。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_dashboard_stats(db: AsyncSession) -> dict:
    today = datetime.now().date().isoformat()
    # 今日新增
    today_created = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM ticket "
                "WHERE CAST(create_at AS DATE) = CAST(:d AS DATE)"
            ),
            {"d": today},
        )
    ).scalar() or 0

    night_auto = (
        await db.execute(
            text("SELECT COUNT(*) FROM ticket WHERE status = 'auto_resolved'")
        )
    ).scalar() or 0

    # 一键执行会写 draft_adopt + one_click_execute；按 one_click 计更贴现主路径
    adopt_n = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM ticket_event "
                "WHERE event_type = 'one_click_execute' "
                "AND CAST(create_at AS DATE) = CAST(:d AS DATE)"
            ),
            {"d": today},
        )
    ).scalar() or 0

    ready_n = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM ticket_event "
                "WHERE event_type = 'draft_ready' "
                "AND CAST(create_at AS DATE) = CAST(:d AS DATE)"
            ),
            {"d": today},
        )
    ).scalar() or 0

    if ready_n > 0:
        adopt_rate = round(float(adopt_n) / float(ready_n), 4)
    elif adopt_n > 0:
        adopt_rate = 1.0
    else:
        adopt_rate = 0.0

    overdue = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM ticket "
                "WHERE status IN ('pending', 'need_manual') "
                "OR (status = 'processing' AND escalate = 1)"
            )
        )
    ).scalar() or 0

    return {
        "today_created": int(today_created),
        "night_auto_resolved": int(night_auto),
        "draft_adopt_rate": float(adopt_rate),
        "overdue_unhandled": int(overdue),
    }
