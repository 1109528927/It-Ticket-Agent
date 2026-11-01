"""LangGraph Checkpointer：图执行快照（同 thread 可续跑）。

与 chat_message 分工：
- chat_message：给人看的会话、按工单查询、前端时间线
- Checkpointer：图节点间状态快照，便于同 thread 断线/重试续跑

默认 SQLite 文件，避免和业务库表混在一起；可用环境变量改路径。
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _BACKEND_ROOT / "data" / "langgraph_checkpoints.sqlite"

_checkpointer: SqliteSaver | None = None
_conn: sqlite3.Connection | None = None


def get_checkpointer() -> SqliteSaver:
    global _checkpointer, _conn
    if _checkpointer is not None:
        return _checkpointer

    path = Path(
        os.getenv("LANGGRAPH_CHECKPOINT_SQLITE", str(_DEFAULT_PATH))
    ).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(path), check_same_thread=False)
    _checkpointer = SqliteSaver(_conn)
    _checkpointer.setup()
    return _checkpointer


def make_thread_id(
    *,
    user_id: int,
    role: str,
    ticket_id: int | None,
    client_thread_id: str | None = None,
) -> str:
    """同一用户+角色+工单共用 thread；前端可回传上次 SSE 的 thread_id。"""
    role = (role or "unknown").strip() or "unknown"
    uid = int(user_id)
    if client_thread_id:
        safe = re.sub(r"[^a-zA-Z0-9_\-:]", "", client_thread_id)[:64]
        if safe:
            # 已是完整 id（上次 SSE 回的）就原样用，避免再包一层
            if safe.startswith(f"u{uid}:"):
                return safe
            return f"u{uid}:{role}:{safe}"
    tid = int(ticket_id) if ticket_id is not None else 0
    return f"u{uid}:{role}:t{tid}"
