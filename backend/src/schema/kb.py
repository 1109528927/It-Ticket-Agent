from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

KbCategory = Literal["account", "device", "network", "permission"]


class KbArticleOut(BaseModel):
    id: int
    category: str
    title: str
    content: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KbListOut(BaseModel):
    items: list[KbArticleOut] = Field(default_factory=list)


class KbArticleIn(BaseModel):
    category: KbCategory
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)

    @field_validator("title", "content")
    @classmethod
    def strip_text(cls, v: str):
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("不能为空")
        return v


class KbIngestJobOut(BaseModel):
    id: int
    category: str
    title: str
    filename: str
    ext: str
    enable_ocr: bool
    status: str
    error_message: Optional[str] = None
    article_id: Optional[int] = None
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KbIngestJobListOut(BaseModel):
    items: list[KbIngestJobOut] = Field(default_factory=list)
