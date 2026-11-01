"""工单自动化：持久化回复草稿、跑批报告。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from model.user import Base


class TicketAssistantDraft(Base):
    """挂在工单上的助手草稿（批跑/初审/对话均可写入）。"""

    __tablename__ = "ticket_assistant_draft"

    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticket.id"), primary_key=True
    )
    draft_type: Mapped[str] = mapped_column(String(32), nullable=False, default="reply")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="batch")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AutomationJobRun(Base):
    __tablename__ = "automation_job_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    trigger_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="cron"
    )
    summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AutomationTicketResult(Base):
    __tablename__ = "automation_ticket_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("automation_job_run.id"), nullable=False
    )
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticket.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    create_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AutomationConfig(Base):
    """单行配置（id 固定为 1）：开关、时段、类别策略，给客服控制台改。"""

    __tablename__ = "automation_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enable_backlog_draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    enable_sla_sweep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_triage_on_create: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # interval：每隔 N 分钟；daily：每天固定时刻（backlog_daily_time）
    backlog_schedule_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="interval"
    )
    backlog_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    backlog_daily_time: Mapped[str] = mapped_column(
        String(8), nullable=False, default="02:00"
    )
    cron_expression: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sla_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15
    )
    skip_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 简单单（非高危语义）起草后自动写 reply 事件；高危仍只起草
    auto_send_simple_reply: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # 夜班：非高危且置信度达标 → 发回复并 status=auto_resolved（仍禁止改密改权）
    enable_night_auto_resolve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    night_confidence_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.8
    )
    # waiting_feedback 超时催办；员工意图结案 / 升级
    enable_feedback_sla: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    feedback_idle_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # JSON 数组字符串，如 ["account","network"]；空表示全部类别
    backlog_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_backlog_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_sla_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
