"""自动化跑批报告查询（异步，给 API）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model.automation import (
    AutomationJobRun,
    AutomationTicketResult,
    TicketAssistantDraft,
)


async def list_job_runs(
    db: AsyncSession, *, limit: int = 30
) -> list[dict[str, Any]]:
    stmt = (
        select(AutomationJobRun)
        .order_by(AutomationJobRun.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = (await db.execute(stmt)).scalars().all()
    out = []
    for r in rows:
        summary = None
        if r.summary_json:
            try:
                summary = json.loads(r.summary_json)
            except json.JSONDecodeError:
                summary = {"raw": r.summary_json}
        out.append(
            {
                "id": r.id,
                "job_type": r.job_type,
                "status": r.status,
                "trigger_source": r.trigger_source,
                "summary": summary,
                "error_message": r.error_message,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
        )
    return out


async def get_job_run(db: AsyncSession, run_id: int) -> dict[str, Any] | None:
    row = await db.get(AutomationJobRun, int(run_id))
    if row is None:
        return None
    summary = None
    if row.summary_json:
        try:
            summary = json.loads(row.summary_json)
        except json.JSONDecodeError:
            summary = {"raw": row.summary_json}
    results = (
        await db.execute(
            select(AutomationTicketResult)
            .where(AutomationTicketResult.run_id == int(run_id))
            .order_by(AutomationTicketResult.id.asc())
        )
    ).scalars().all()
    return {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "trigger_source": row.trigger_source,
        "summary": summary,
        "error_message": row.error_message,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "results": [
            {
                "id": x.id,
                "run_id": x.run_id,
                "ticket_id": x.ticket_id,
                "action": x.action,
                "success": x.success,
                "detail": x.detail,
                "create_at": x.create_at,
            }
            for x in results
        ],
    }


async def get_ticket_draft(
    db: AsyncSession, ticket_id: int
) -> dict[str, Any] | None:
    row = await db.get(TicketAssistantDraft, int(ticket_id))
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
