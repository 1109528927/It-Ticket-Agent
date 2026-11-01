from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from model.user import Base


class Ticket(Base):
    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # 1=需人工升级关注（员工仍未解决 / SLA 升级）；列表可高亮
    escalate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TicketEvent(Base):
    __tablename__ = "ticket_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TicketAction(Base):
    __tablename__ = "ticket_action"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket.id"), nullable=False)
    proposer_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    execution_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    execution_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TicketChecklist(Base):
    """设备 / 网络类处理清单项。"""

    __tablename__ = "ticket_checklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket.id"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
