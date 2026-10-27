from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.kb import (
    create_kb_article,
    delete_kb_article,
    get_kb_article,
    list_kb_articles,
    update_kb_article,
)
from crud.kb_ingest import (
    create_ingest_job,
    get_ingest_job,
    list_ingest_jobs,
    mark_ingest_failed_early,
    update_ingest_stored_path,
)
from model.user import User
from schema.kb import (
    KbArticleIn,
    KbArticleOut,
    KbIngestJobListOut,
    KbIngestJobOut,
    KbListOut,
)
from utils.auth import get_current_user
from utils.kb_ingest import dispatch_ingest, save_upload
from utils.kb_parse import assert_allowed
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


@router.post("/ingest")
async def ingest_kb_file(
    background_tasks: BackgroundTasks,
    category: str = Form(...),
    title: str | None = Form(default=None),
    enable_ocr: str = Form(default="false"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传 PDF/DOCX/MD/图片：先受理，后台解析切分嵌入。"""
    _require_support(user)
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="类别不合法")
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    try:
        ext = assert_allowed(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ocr_on = str(enable_ocr).strip().lower() in ("1", "true", "yes", "on")
    stem_title = (title or Path(file.filename).stem or "未命名手册").strip()[:200]
    if not stem_title:
        stem_title = "未命名手册"

    job = await create_ingest_job(
        db,
        category=category,
        title=stem_title,
        filename=file.filename,
        stored_path="",
        ext=ext,
        enable_ocr=ocr_on,
        created_by=user.id,
    )
    try:
        safe_name, stored_path, ext = await save_upload(job.id, file)
        await update_ingest_stored_path(
            db, job, filename=safe_name, stored_path=stored_path, ext=ext
        )
    except ValueError as e:
        await mark_ingest_failed_early(db, job, str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        await mark_ingest_failed_early(db, job, f"保存文件失败: {e}")
        raise HTTPException(status_code=500, detail="保存文件失败") from e

    mode = dispatch_ingest(job.id, background_tasks)
    return success_response(
        message="已受理",
        data={
            "job_id": job.id,
            "status": "pending",
            "queue": mode,
        },
    )


@router.get("/ingest/jobs")
async def ingest_job_list(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    rows = await list_ingest_jobs(db, limit=limit)
    payload = KbIngestJobListOut(
        items=[KbIngestJobOut.model_validate(r) for r in rows]
    )
    return success_response(message="ok", data=payload.model_dump())


@router.get("/ingest/jobs/{job_id}")
async def ingest_job_detail(
    job_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    row = await get_ingest_job(db, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success_response(
        message="ok",
        data=KbIngestJobOut.model_validate(row).model_dump(),
    )


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
