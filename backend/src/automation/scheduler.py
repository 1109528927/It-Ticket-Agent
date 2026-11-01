"""APScheduler：每分钟醒一次，读 automation_config 再决定是否跑。"""

from __future__ import annotations

import logging

from automation.config import AUTOMATION_ENABLED

logger = logging.getLogger(__name__)

_scheduler = None


def _tick() -> None:
    """配置驱动：开关关了就静默退出；开了才按间隔/每日时刻触发。"""
    from automation.runner import run_backlog_job, run_sla_job
    from automation.settings_store import (
        load_config_sync,
        mark_last_run,
        should_run_backlog_now,
        should_run_sla_now,
    )

    cfg = load_config_sync()
    try:
        if should_run_backlog_now(cfg):
            logger.info("automation tick: backlog_draft")
            run_backlog_job(trigger_source="cron")
            mark_last_run(job="backlog")
    except Exception:
        logger.exception("automation tick backlog failed")
    # 重新读一次，避免上面更新 last_run 后 SLA 用旧对象也无妨
    cfg = load_config_sync()
    try:
        if should_run_sla_now(cfg):
            logger.info("automation tick: sla_sweep")
            run_sla_job(trigger_source="cron")
            mark_last_run(job="sla")
    except Exception:
        logger.exception("automation tick sla failed")


def start_scheduler() -> None:
    global _scheduler
    if not AUTOMATION_ENABLED:
        logger.info("AUTOMATION_ENABLED=0，跳过调度器")
        return
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    sched.add_job(
        _tick,
        "interval",
        minutes=1,
        id="automation_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    logger.info("automation scheduler started (1min tick, config-driven)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("automation scheduler stopped")
