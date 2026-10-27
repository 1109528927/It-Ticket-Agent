"""知识库入库任务：受理入队、后台解析切分嵌入。"""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile

from utils import milvus_kb
from utils.kb_parse import ALLOWED_EXTS, assert_allowed, parse_file

logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path(
    os.getenv(
        "KB_UPLOAD_DIR",
        str(Path(__file__).resolve().parents[2] / "uploads" / "kb"),
    )
)
MAX_UPLOAD_BYTES = int(os.getenv("KB_MAX_UPLOAD_MB", "20")) * 1024 * 1024
REDIS_QUEUE_KEY = os.getenv("KB_INGEST_REDIS_KEY", "kb:ingest")
CONTENT_DB_LIMIT = int(os.getenv("KB_CONTENT_DB_LIMIT", "60000"))


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\u4e00-\u9fff\-]+", "_", base, flags=re.UNICODE)
    return (base or "file")[:180]


def ensure_upload_dir(job_id: int) -> Path:
    d = UPLOAD_ROOT / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_upload(job_id: int, file: UploadFile) -> tuple[str, str, str]:
    """落盘，返回 (safe_name, stored_path, ext)。"""
    assert_allowed(file.filename or "")
    ext = assert_allowed(file.filename or "")
    safe = _safe_filename(file.filename or f"upload{ext}")
    folder = ensure_upload_dir(job_id)
    dest = folder / safe

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(
                    f"文件过大，上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB"
                )
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise ValueError("空文件")
    return safe, str(dest), ext


def dispatch_ingest(job_id: int, background_tasks: BackgroundTasks | None = None) -> str:
    """优先 Redis 列表；否则 BackgroundTasks；再否则当前进程同步跑（脚本用）。"""
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if redis_url:
        try:
            import redis

            client = redis.from_url(redis_url, decode_responses=True)
            client.lpush(REDIS_QUEUE_KEY, str(job_id))
            logger.info("入库任务入 Redis 队列 job_id=%s", job_id)
            return "redis"
        except Exception:
            logger.exception("Redis 入队失败，改本地后台 job_id=%s", job_id)

    if background_tasks is not None:
        background_tasks.add_task(run_ingest_job, job_id)
        return "background"

    run_ingest_job(job_id)
    return "sync"


def run_ingest_job(job_id: int) -> None:
    """同步执行单条任务（BackgroundTasks / Redis worker 共用）。"""
    from config.request import SyncSessionLocal
    from model.kb import KbArticle, KbIngestJob

    with SyncSessionLocal() as db:
        job = db.get(KbIngestJob, job_id)
        if not job:
            logger.error("入库任务不存在 job_id=%s", job_id)
            return
        if job.status not in ("pending", "failed"):
            logger.info("跳过非待处理任务 job_id=%s status=%s", job_id, job.status)
            return
        job.status = "running"
        job.error_message = None
        db.commit()

        try:
            text = parse_file(job.stored_path, enable_ocr=bool(job.enable_ocr))
            content = text[:CONTENT_DB_LIMIT]
            title = (job.title or Path(job.filename).stem)[:200]

            article: KbArticle | None = None
            if job.article_id:
                article = db.get(KbArticle, job.article_id)
            if article is None:
                article = KbArticle(
                    category=job.category,
                    title=title,
                    content=content,
                )
                db.add(article)
                db.flush()
            else:
                article.category = job.category
                article.title = title
                article.content = content
                article.updated_at = datetime.now()

            sync_stats = milvus_kb.replace_article_chunks(
                article.id, article.category, article.title, article.content
            )

            job.article_id = article.id
            job.chunk_count = int(sync_stats.get("chunk_count") or 0)
            job.status = "succeeded"
            job.finished_at = datetime.now()
            job.error_message = None
            db.commit()
            logger.info(
                "入库成功 job_id=%s article_id=%s chunks=%s embedded=%s reused=%s deleted=%s",
                job_id,
                article.id,
                sync_stats.get("chunk_count"),
                sync_stats.get("embedded"),
                sync_stats.get("reused"),
                sync_stats.get("deleted"),
            )
        except Exception as e:
            logger.exception("入库失败 job_id=%s", job_id)
            db.rollback()
            job = db.get(KbIngestJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)[:2000]
                job.finished_at = datetime.now()
                db.commit()


def remove_job_files(stored_path: str) -> None:
    """可选清理；默认保留便于排障。"""
    try:
        p = Path(stored_path)
        if p.is_file():
            folder = p.parent
            p.unlink(missing_ok=True)
            if folder.exists() and not any(folder.iterdir()):
                shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        logger.exception("清理上传文件失败 path=%s", stored_path)


# 给类型检查 / 文档用
_ = ALLOWED_EXTS
