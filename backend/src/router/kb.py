from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.kb import (
    create_kb_article,
    delete_kb_article,
    get_kb_article,
    list_kb_articles,
    update_kb_article,
)
from model.user import User
from schema.kb import KbArticleIn, KbArticleOut, KbListOut
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/kb", tags=["kb"])

CATEGORIES = {"account", "device", "network", "permission"}


def _require_support(user: User) -> None:
    if user.role != "support":
        raise HTTPException(status_code=403, detail="只有客服可以管理知识库")


@router.get("")
async def list_kb(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="类别不合法")

    rows = await list_kb_articles(db, category=category, q=q)
    payload = KbListOut(items=[KbArticleOut.model_validate(row) for row in rows])
    return success_response(message="ok", data=payload.model_dump())


@router.get("/{article_id}")
async def get_kb(
    article_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await get_kb_article(db, article_id)
    if not row:
        raise HTTPException(status_code=404, detail="文章不存在")
    return success_response(
        message="ok",
        data=KbArticleOut.model_validate(row).model_dump(),
    )


@router.post("")
async def create_kb(
    body: KbArticleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await create_kb_article(
        db,
        category=body.category,
        title=body.title,
        content=body.content,
    )
    return success_response(
        message="创建成功",
        data=KbArticleOut.model_validate(row).model_dump(),
    )


@router.put("/{article_id}")
async def update_kb(
    article_id: int,
    body: KbArticleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await update_kb_article(
        db,
        article_id=article_id,
        category=body.category,
        title=body.title,
        content=body.content,
    )
    if not row:
        raise HTTPException(status_code=404, detail="文章不存在")
    return success_response(
        message="保存成功",
        data=KbArticleOut.model_validate(row).model_dump(),
    )


@router.delete("/{article_id}")
async def remove_kb(
    article_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    ok = await delete_kb_article(db, article_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文章不存在")
    return success_response(message="已删除")
