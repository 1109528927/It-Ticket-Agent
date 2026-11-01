"""跑批编排：写 automation_job_run + 逐票结果。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

from config.request import SyncSessionLocal
from model.automation import AutomationJobRun, AutomationTicketResult

logger = logging.getLogger(__name__)


def _persist_results(run_id: int, results: list[dict[str, Any]]) -> None:
    with SyncSessionLocal() as db:
        for r in results:
            db.add(
                AutomationTicketResult(
                    run_id=run_id,
                    ticket_id=int(r["ticket_id"]),
                    action=str(r.get("action") or "unknown"),
                    success=bool(r.get("success", True)),
                    detail=(r.get("detail") or "")[:2000] or None,
                )
            )
        db.commit()


def execute_job(
    *,
    job_type: str,
    trigger_source: str,
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    with SyncSessionLocal() as db:
        run = AutomationJobRun(
            job_type=job_type,
            status="running",
            trigger_source=trigger_source,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = int(run.id)

    try:
        payload = fn() or {}
        results = list(payload.get("results") or [])
        if results:
            _persist_results(run_id, results)
        summary = {
            "scanned": payload.get("scanned", len(results)),
            "ok": payload.get("ok"),
            "failed": payload.get("failed"),
        }
        with SyncSessionLocal() as db:
            row = db.get(AutomationJobRun, run_id)
            if row:
                row.status = "succeeded"
                row.summary_json = json.dumps(summary, ensure_ascii=False)
                row.finished_at = datetime.now()
                db.commit()
        return {"run_id": run_id, "status": "succeeded", **summary, "results": results}
    except Exception as e:
        logger.exception("automation job failed type=%s", job_type)
        with SyncSessionLocal() as db:
            row = db.get(AutomationJobRun, run_id)
            if row:
                row.status = "failed"
                row.error_message = f"{type(e).__name__}: {e}"[:2000]
                row.finished_at = datetime.now()
                db.commit()
        return {
            "run_id": run_id,
            "status": "failed",
            "error": str(e),
            "scanned": 0,
            "ok": 0,
            "failed": 0,
            "results": [],
        }


def run_backlog_job(*, trigger_source: str = "cron") -> dict[str, Any]:
    from automation.backlog_batch import run_backlog_batch

    return execute_job(
        job_type="backlog_draft",
        trigger_source=trigger_source,
        fn=run_backlog_batch,
    )


def run_sla_job(*, trigger_source: str = "cron") -> dict[str, Any]:
    from automation.sla import run_sla_sweep

    return execute_job(
        job_type="sla_sweep",
        trigger_source=trigger_source,
        fn=run_sla_sweep,
    )
