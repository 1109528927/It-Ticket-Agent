from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AutomationRunOut(BaseModel):
    id: int
    job_type: str
    status: str
    trigger_source: str
    summary: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class AutomationResultOut(BaseModel):
    id: int
    run_id: int
    ticket_id: int
    action: str
    success: bool
    detail: Optional[str] = None
    create_at: Optional[datetime] = None


class TicketAssistantDraftOut(BaseModel):
    ticket_id: int
    draft_type: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)
    source: str
    updated_at: Optional[str] = None


class AutomationConfigOut(BaseModel):
    id: int = 1
    enable_backlog_draft: bool = True
    enable_sla_sweep: bool = True
    enable_triage_on_create: bool = True
    backlog_schedule_mode: str = "interval"
    backlog_interval_minutes: int = 60
    backlog_daily_time: str = "02:00"
    cron_expression: Optional[str] = None
    sla_interval_minutes: int = 15
    skip_high_risk: bool = False
    auto_send_simple_reply: bool = False
    backlog_categories: List[str] = Field(default_factory=list)
    last_backlog_run_at: Optional[datetime] = None
    last_sla_run_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AutomationConfigUpdate(BaseModel):
    enable_backlog_draft: bool = True
    enable_sla_sweep: bool = True
    enable_triage_on_create: bool = True
    backlog_schedule_mode: str = Field(default="interval")
    backlog_interval_minutes: int = Field(default=60, ge=5, le=24 * 60)
    backlog_daily_time: str = Field(default="02:00")
    sla_interval_minutes: int = Field(default=15, ge=5, le=24 * 60)
    skip_high_risk: bool = False
    auto_send_simple_reply: bool = False
    backlog_categories: List[str] = Field(default_factory=list)
