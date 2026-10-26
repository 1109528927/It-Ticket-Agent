"""对话落库同步 CRUD（给 Agent 图 / SSE 用，不 await）。"""

from sqlalchemy import select

from config.request import SyncSessionLocal
from model.chat import ChatMessageRow

_LOAD_LIMIT = 40


def save_chat_message(
    *,
    user_id: int,
    role: str,
    content: str,
    kind: str = "full",
    ticket_id: int | None = None,
) -> None:
    content = (content or "").strip()
    if not content:
        return
    with SyncSessionLocal() as db:
        db.add(
            ChatMessageRow(
                user_id=user_id,
                ticket_id=ticket_id,
                role=role,
                content=content[:8000],
                kind=kind,
            )
        )
        db.commit()


def list_chat_messages(
    *,
    user_id: int,
    ticket_id: int | None = None,
    include_progress: bool = False,
    limit: int = _LOAD_LIMIT,
) -> list[dict]:
    """默认跳过 progress。摘要 kind=summary 会带上，供压缩管线使用。"""
    with SyncSessionLocal() as db:
        stmt = select(ChatMessageRow).where(ChatMessageRow.user_id == user_id)
        if ticket_id is not None:
            stmt = stmt.where(ChatMessageRow.ticket_id == ticket_id)
        else:
            stmt = stmt.where(ChatMessageRow.ticket_id.is_(None))
        if not include_progress:
            stmt = stmt.where(ChatMessageRow.kind != "progress")
        stmt = stmt.order_by(ChatMessageRow.id.desc()).limit(limit)
        rows = list(reversed(db.execute(stmt).scalars().all()))
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "kind": r.kind,
            "ticket_id": r.ticket_id,
        }
        for r in rows
    ]
