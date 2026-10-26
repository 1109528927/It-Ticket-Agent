from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from model.kb import KbArticle
from utils import milvus_kb


async def list_kb_articles(
    db: AsyncSession,
    *,
    category: str | None = None,
    q: str | None = None,
) -> list[KbArticle]:
    stmt = select(KbArticle)
    if category:
        stmt = stmt.where(KbArticle.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(KbArticle.title.like(like), KbArticle.content.like(like))
        )
    stmt = stmt.order_by(KbArticle.updated_at.desc(), KbArticle.id.desc())
    return list((await db.execute(stmt)).scalars().all())


async def get_kb_article(db: AsyncSession, article_id: int) -> KbArticle | None:
    stmt = select(KbArticle).where(KbArticle.id == article_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_kb_article(
    db: AsyncSession,
    *,
    category: str,
    title: str,
    content: str,
) -> KbArticle:
    article = KbArticle(category=category, title=title, content=content)
    db.add(article)
    await db.flush()
    await db.refresh(article)
    milvus_kb.upsert_article(article.id, article.category, article.title, article.content)
    return article


async def update_kb_article(
    db: AsyncSession,
    *,
    article_id: int,
    category: str,
    title: str,
    content: str,
) -> KbArticle | None:
    article = await get_kb_article(db, article_id)
    if not article:
        return None
    article.category = category
    article.title = title
    article.content = content
    article.updated_at = datetime.now()
    await db.flush()
    await db.refresh(article)
    milvus_kb.upsert_article(article.id, article.category, article.title, article.content)
    return article


async def delete_kb_article(db: AsyncSession, article_id: int) -> bool:
    article = await get_kb_article(db, article_id)
    if not article:
        return False
    await db.delete(article)
    await db.flush()
    milvus_kb.delete_article(article_id)
    return True


async def search_kb(
    db: AsyncSession,
    *,
    q: str,
    category: str | None = None,
    limit: int = 3,
    snippet: int = 200,
) -> list[dict]:
    """助手只读检索。先走 MySQL 关键字；Milvus 可用后再换向量。"""
    rows = await list_kb_articles(db, category=category, q=q)
    out: list[dict] = []
    for row in rows[:limit]:
        text = row.content or ""
        if len(text) > snippet:
            text = text[:snippet] + "…"
        out.append(
            {
                "id": row.id,
                "category": row.category,
                "title": row.title,
                "content": text,
            }
        )
    return out
