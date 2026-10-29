from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from model.user import Base


class ChatMessageRow(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="full")
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentTurnLog(Base):
    """每轮调用记账：工具、检索条数、HITL、粗算 token。"""

    __tablename__ = "agent_turn_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    ticket_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    kb_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hitl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
