from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model.kb import KbIngestJob


async def create_ingest_job(
    db: AsyncSession,
    *,
    category: str,
    title: str,
    filename: str,
    stored_path: str,
    ext: str,
    enable_ocr: bool,
    created_by: int | None,
) -> KbIngestJob:
    job = KbIngestJob(
        category=category,
        title=title,
        filename=filename,
        stored_path=stored_path or "",
        ext=ext,
        enable_ocr=enable_ocr,
        status="pending",
        created_by=created_by,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


async def update_ingest_stored_path(
    db: AsyncSession, job: KbIngestJob, *, filename: str, stored_path: str, ext: str
) -> KbIngestJob:
    job.filename = filename
    job.stored_path = stored_path
    job.ext = ext
    await db.flush()
    await db.refresh(job)
    return job


async def get_ingest_job(db: AsyncSession, job_id: int) -> KbIngestJob | None:
    return await db.get(KbIngestJob, job_id)


async def list_ingest_jobs(
    db: AsyncSession, *, limit: int = 20
) -> list[KbIngestJob]:
    stmt = (
        select(KbIngestJob)
        .order_by(KbIngestJob.id.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def mark_ingest_failed_early(
    db: AsyncSession, job: KbIngestJob, message: str
) -> None:
    job.status = "failed"
    job.error_message = message[:2000]
    job.finished_at = datetime.now()
    await db.flush()
