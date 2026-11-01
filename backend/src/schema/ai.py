from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class ChatRequest(BaseModel):
    """多轮历史。role 只允许 user / assistant。"""

    messages: list[ChatMessage] = Field(default_factory=list)
    ticket_id: int | None = Field(default=None, description="可选，当前关联工单号")
    thread_id: str | None = Field(
        default=None,
        description="可选，LangGraph Checkpointer 线程号；同轮重试可复用",
        max_length=64,
    )
