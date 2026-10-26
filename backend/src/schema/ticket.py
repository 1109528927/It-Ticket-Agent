import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["account", "device", "network", "permission"]
Priority = Literal["low", "medium", "high"]

_GROUP_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{2,64}$")
_SENSITIVE_KEYS = {"password", "passwd", "card_no", "card_number", "cvv"}


class TicketListItem(BaseModel):
    id: int
    title: str
    category: str
    status: str
    priority: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TicketListOut(BaseModel):
    items: list[TicketListItem] = Field(default_factory=list)


class TicketCreateIn(BaseModel):
    category: Category
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    priority: Priority = "medium"

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class TicketEventOut(BaseModel):
    id: int
    event_type: str
    detail: Optional[str] = None
    actor_id: int
    create_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TicketActionOut(BaseModel):
    id: int
    ticket_id: int
    proposer_id: int
    action_type: str
    reason: str
    payload: Optional[dict[str, Any]] = None
    status: str
    execution_status: Optional[str] = None
    # 第二版：结构化执行结果（含 message），兼容旧字符串
    execution_result: Optional[Any] = None
    create_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChecklistItemOut(BaseModel):
    id: int
    ticket_id: int
    item_key: str
    label: str
    checked: bool
    updated_at: Optional[datetime] = None


class TicketDetailOut(BaseModel):
    id: int
    title: str
    category: str
    description: str
    status: str
    priority: str
    user_id: Optional[int] = None
    creator_username: Optional[str] = None
    creator_employee_no: Optional[str] = None
    create_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    events: list[TicketEventOut] = Field(default_factory=list)
    actions: list[TicketActionOut] = Field(default_factory=list)
    checklist: list[ChecklistItemOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChecklistToggleIn(BaseModel):
    checked: bool


class EmployeeReopenIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="仍未解决的原因")

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class TicketCommentIn(BaseModel):
    detail: str = Field(min_length=1, max_length=2000, description="补充说明")

    @field_validator("detail")
    @classmethod
    def strip_detail(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


TicketStatus = Literal[
    "pending",
    "processing",
    "pending_confirm",
    "resolved",
    "closed",
]


class TicketStatusIn(BaseModel):
    status: TicketStatus = Field(description="目标状态")


class TicketReplyIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="回复内容")

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


ACTION_TYPES = {"reset_password", "change_permission", "refund"}


class TicketActionProposeIn(BaseModel):
    action_type: str
    reason: str = Field(min_length=1, max_length=500)
    payload: Optional[dict[str, Any]] = None

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v

    @field_validator("action_type")
    @classmethod
    def check_action_type(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if v not in ACTION_TYPES:
            raise ValueError("action_type 不在白名单")
        return v

    @model_validator(mode="after")
    def validate_payload(self):
        payload = self.payload or {}
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是对象")
        lowered = {str(k).lower() for k in payload}
        bad = lowered & _SENSITIVE_KEYS
        if bad:
            raise ValueError(f"payload 不允许包含敏感字段：{', '.join(sorted(bad))}")

        if self.action_type == "reset_password":
            # 前端可带工号；后端提出时会强制改成提单人工号，防篡改
            target = str(payload.get("target_employee_no", "")).strip()
            if target and len(target) > 50:
                raise ValueError("target_employee_no 过长")
            self.payload = {"target_employee_no": target} if target else {}
        elif self.action_type == "change_permission":
            group = str(payload.get("group_name", "")).strip()
            if not _GROUP_NAME_RE.match(group):
                raise ValueError("权限组名不合法（2～64 位字母数字下划线或短横线）")
            self.payload = {"group_name": group}
        elif self.action_type == "refund":
            raw = payload.get("amount")
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                raise ValueError("退款需要 amount")
            try:
                amount = Decimal(str(raw).strip())
            except (InvalidOperation, ValueError):
                raise ValueError("退款金额格式不正确") from None
            if amount <= 0:
                raise ValueError("退款金额必须大于 0")
            quantized = amount.quantize(Decimal("0.01"))
            if quantized != amount:
                raise ValueError("退款金额最多两位小数")
            self.payload = {"amount": f"{quantized:.2f}"}
        return self


class TicketActionRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="拒绝理由")

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class TicketActionConfirmIn(BaseModel):
    """确认高风险。重置密码时必填临时新密码（不落 payload 长期存库）。"""

    new_password: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=64,
        description="临时新密码，仅 reset_password 需要",
    )

    @field_validator("new_password")
    @classmethod
    def strip_password(cls, v: Optional[str]):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
        if not v:
            return None
        return v
