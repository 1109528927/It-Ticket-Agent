"""知识库同步关键字检索：Milvus 不可用时给 Agent 工具降级用。"""

from __future__ import annotations

from sqlalchemy import or_, select

from config.request import SyncSessionLocal
from model.kb import KbArticle


def search_kb_keyword(
    q: str,
    *,
    category: str | None = None,
    limit: int = 3,
    snippet: int = 400,
) -> list[dict]:
    """标题 / 正文 LIKE；返回与向量命中相近的字段，方便统一格式化引用。"""
    q = (q or "").strip()
    if not q:
        return []
    with SyncSessionLocal() as db:
        stmt = select(KbArticle)
        if category:
            stmt = stmt.where(KbArticle.category == category)
        like = f"%{q}%"
        stmt = stmt.where(
            or_(KbArticle.title.like(like), KbArticle.content.like(like))
        )
        stmt = stmt.order_by(KbArticle.updated_at.desc(), KbArticle.id.desc()).limit(
            limit
        )
        rows = list(db.execute(stmt).scalars().all())

    out: list[dict] = []
    for row in rows:
        text = f"{row.title}\n{row.content or ''}".strip()
        if len(text) > snippet:
            text = text[:snippet] + "…"
        out.append(
            {
                "id": row.id,
                "text": text,
                "source": f"kb_article:{row.id}",
                "category": row.category,
                "cite_id": f"kb_article:{row.id}",
                "via": "keyword",
            }
        )
    return out
