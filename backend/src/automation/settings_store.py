"""从 DB 读/写自动化配置；调度与批跑都走这里，不写死在代码里。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from automation.config import (
    BATCH_INTERVAL_MINUTES,
    SLA_INTERVAL_MINUTES,
    TRIAGE_ON_CREATE,
)
from config.request import SyncSessionLocal
from model.automation import AutomationConfig

logger = logging.getLogger(__name__)

_ALLOWED_CATEGORIES = frozenset({"account", "device", "network", "permission"})
_CONFIG_ID = 1


def _defaults() -> dict[str, Any]:
    return {
        "id": _CONFIG_ID,
        "enable_backlog_draft": True,
        "enable_sla_sweep": True,
        "enable_triage_on_create": TRIAGE_ON_CREATE,
        "backlog_schedule_mode": "interval",
        "backlog_interval_minutes": max(5, BATCH_INTERVAL_MINUTES),
        "backlog_daily_time": "02:00",
        "cron_expression": "0 2 * * *",
        "sla_interval_minutes": max(5, SLA_INTERVAL_MINUTES),
        "skip_high_risk": False,
        "auto_send_simple_reply": False,
        "backlog_categories": [],
        "last_backlog_run_at": None,
        "last_sla_run_at": None,
        "updated_at": None,
    }


def _parse_categories(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x) in _ALLOWED_CATEGORIES]
    except json.JSONDecodeError:
        pass
    return [
        p.strip()
        for p in str(raw).split(",")
        if p.strip() in _ALLOWED_CATEGORIES
    ]


def _row_to_dict(row: AutomationConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "enable_backlog_draft": bool(row.enable_backlog_draft),
        "enable_sla_sweep": bool(row.enable_sla_sweep),
        "enable_triage_on_create": bool(row.enable_triage_on_create),
        "backlog_schedule_mode": row.backlog_schedule_mode or "interval",
        "backlog_interval_minutes": int(row.backlog_interval_minutes or 60),
        "backlog_daily_time": (row.backlog_daily_time or "02:00")[:5],
        "cron_expression": row.cron_expression,
        "sla_interval_minutes": int(row.sla_interval_minutes or 15),
        "skip_high_risk": bool(row.skip_high_risk),
        "auto_send_simple_reply": bool(
            getattr(row, "auto_send_simple_reply", False)
        ),
        "backlog_categories": _parse_categories(row.backlog_categories),
        "last_backlog_run_at": row.last_backlog_run_at,
        "last_sla_run_at": row.last_sla_run_at,
        "updated_at": row.updated_at,
    }


def _daily_to_cron(hhmm: str) -> str:
    parts = (hhmm or "02:00").strip().split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        h, m = 2, 0
    h = max(0, min(23, h))
    m = max(0, min(59, m))
    return f"{m} {h} * * *"


def ensure_config_row(db) -> AutomationConfig:
    row = db.get(AutomationConfig, _CONFIG_ID)
    if row is not None:
        return row
    d = _defaults()
    row = AutomationConfig(
        id=_CONFIG_ID,
        enable_backlog_draft=d["enable_backlog_draft"],
        enable_sla_sweep=d["enable_sla_sweep"],
        enable_triage_on_create=d["enable_triage_on_create"],
        backlog_schedule_mode=d["backlog_schedule_mode"],
        backlog_interval_minutes=d["backlog_interval_minutes"],
        backlog_daily_time=d["backlog_daily_time"],
        cron_expression=d["cron_expression"],
        sla_interval_minutes=d["sla_interval_minutes"],
        skip_high_risk=d["skip_high_risk"],
        auto_send_simple_reply=d["auto_send_simple_reply"],
        backlog_categories=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def load_config_sync() -> dict[str, Any]:
    try:
        with SyncSessionLocal() as db:
            row = ensure_config_row(db)
            return _row_to_dict(row)
    except Exception:
        logger.exception("load automation_config failed, use defaults")
        return _defaults()


def save_config_sync(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("backlog_schedule_mode") or "interval").strip()
    if mode not in {"interval", "daily"}:
        mode = "interval"
    daily = str(payload.get("backlog_daily_time") or "02:00").strip()[:5]
    if len(daily) == 4 and daily[1] == ":":
        daily = f"0{daily}"
    cats = payload.get("backlog_categories") or []
    if isinstance(cats, str):
        cats = _parse_categories(cats)
    else:
        cats = [str(c) for c in cats if str(c) in _ALLOWED_CATEGORIES]
    cats_json = json.dumps(cats, ensure_ascii=False) if cats else None

    with SyncSessionLocal() as db:
        row = ensure_config_row(db)
        row.enable_backlog_draft = bool(payload.get("enable_backlog_draft", True))
        row.enable_sla_sweep = bool(payload.get("enable_sla_sweep", True))
        row.enable_triage_on_create = bool(
            payload.get("enable_triage_on_create", True)
        )
        row.backlog_schedule_mode = mode
        row.backlog_interval_minutes = max(
            5, int(payload.get("backlog_interval_minutes") or 60)
        )
        row.backlog_daily_time = daily
        row.cron_expression = _daily_to_cron(daily)
        row.sla_interval_minutes = max(
            5, int(payload.get("sla_interval_minutes") or 15)
        )
        row.skip_high_risk = bool(payload.get("skip_high_risk", False))
        row.auto_send_simple_reply = bool(
            payload.get("auto_send_simple_reply", False)
        )
        row.backlog_categories = cats_json
        row.updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        return _row_to_dict(row)


def mark_last_run(*, job: str) -> None:
    now = datetime.now()
    with SyncSessionLocal() as db:
        row = ensure_config_row(db)
        if job == "backlog":
            row.last_backlog_run_at = now
        elif job == "sla":
            row.last_sla_run_at = now
        row.updated_at = now
        db.commit()


def should_run_backlog_now(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    if not cfg.get("enable_backlog_draft"):
        return False
    now = now or datetime.now()
    last = cfg.get("last_backlog_run_at")
    mode = cfg.get("backlog_schedule_mode") or "interval"
    if mode == "daily":
        hhmm = (cfg.get("backlog_daily_time") or "02:00")[:5]
        try:
            th, tm = [int(x) for x in hhmm.split(":")[:2]]
        except ValueError:
            th, tm = 2, 0
        if now.hour != th or now.minute != tm:
            return False
        if last and last.date() == now.date():
            return False
        return True
    mins = max(5, int(cfg.get("backlog_interval_minutes") or 60))
    if last is None:
        return True
    return (now - last).total_seconds() >= mins * 60


def should_run_sla_now(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    if not cfg.get("enable_sla_sweep"):
        return False
    now = now or datetime.now()
    last = cfg.get("last_sla_run_at")
    mins = max(5, int(cfg.get("sla_interval_minutes") or 15))
    if last is None:
        return True
    return (now - last).total_seconds() >= mins * 60
