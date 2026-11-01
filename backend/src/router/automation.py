"""自动化：配置台、手动触发批跑/SLA、查看跑批报告、读工单草稿。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.automation import get_job_run, get_ticket_draft, list_job_runs
from model.user import User
from schema.automation import (
    AutomationConfigOut,
    AutomationConfigUpdate,
    AutomationRunOut,
    TicketAssistantDraftOut,
)
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _require_support(user: User) -> None:
    if user.role != "support":
        raise HTTPException(status_code=403, detail="仅客服可操作自动化")


@router.get("/config")
async def api_get_config(user: User = Depends(get_current_user)):
    _require_support(user)
    from automation.settings_store import load_config_sync

    cfg = await asyncio.to_thread(load_config_sync)
    data = AutomationConfigOut.model_validate(cfg).model_dump()
    return success_response(message="ok", data=data)


@router.put("/config")
async def api_put_config(
    body: AutomationConfigUpdate,
    user: User = Depends(get_current_user),
):
    _require_support(user)
    from automation.settings_store import save_config_sync

    mode = (body.backlog_schedule_mode or "interval").strip()
    if mode not in {"interval", "daily"}:
        raise HTTPException(status_code=400, detail="调度方式只能选「每隔多久」或「每天固定时刻」")
    allowed = {"account", "device", "network", "permission"}
    bad = [c for c in body.backlog_categories if c not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"不支持的工单类别：{','.join(bad)}")

    cfg = await asyncio.to_thread(save_config_sync, body.model_dump())
    data = AutomationConfigOut.model_validate(cfg).model_dump()
    return success_response(message="自动化设置已保存", data=data)


@router.get("/runs")
async def api_list_runs(
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    rows = await list_job_runs(db, limit=limit)
    data = [AutomationRunOut.model_validate(r).model_dump() for r in rows]
    return success_response(message="ok", data={"items": data})


@router.get("/runs/{run_id}")
async def api_get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await get_job_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="跑批记录不存在")
    return success_response(message="ok", data=row)


@router.post("/jobs/backlog")
async def api_run_backlog(user: User = Depends(get_current_user)):
    """手动触发积压单草稿批跑（完整跑完再返回摘要）。"""
    _require_support(user)
    from automation.runner import run_backlog_job

    result = await asyncio.to_thread(run_backlog_job, trigger_source="manual")
    return success_response(message="批跑完成", data=result)


@router.post("/jobs/sla")
async def api_run_sla(user: User = Depends(get_current_user)):
    _require_support(user)
    from automation.runner import run_sla_job

    result = await asyncio.to_thread(run_sla_job, trigger_source="manual")
    return success_response(message="SLA 巡检完成", data=result)


@router.post("/tickets/{ticket_id}/triage")
async def api_retriage(ticket_id: int, user: User = Depends(get_current_user)):
    _require_support(user)
    from automation.triage import run_triage_for_ticket

    try:
        result = await asyncio.to_thread(run_triage_for_ticket, ticket_id)
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="工单不存在") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"初审失败：{e}") from e
    return success_response(message="初审完成", data=result)


@router.get("/tickets/{ticket_id}/draft")
async def api_ticket_draft(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await get_ticket_draft(db, ticket_id)
    if row is None:
        return success_response(message="ok", data=None)
    data = TicketAssistantDraftOut.model_validate(row).model_dump()
    return success_response(message="ok", data=data)
