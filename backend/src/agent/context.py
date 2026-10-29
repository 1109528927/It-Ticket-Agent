"""上下文装配 + Token 防爆管线（load_context 里绞 messages）。"""

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent.state import TicketAgentState
from config.request import SyncSessionLocal
from crud.chat_sync import list_chat_messages, save_chat_message
from model.ticket import Ticket

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_ALLOWED_CATEGORIES = frozenset({"account", "device", "network", "permission"})
_TOOL_KEEP = 2
_SUMMARY_TRIGGER = 12
_KEEP_TAIL = 6
_OMIT = "[已省略较早的工具结果]"


class DialogSummary(BaseModel):
    summary: str = Field(description="用户诉求与已确认事实的短摘要")


def _read_skill(category: str) -> str | None:
    if category not in _ALLOWED_CATEGORIES:
        return None
    path = _SKILLS_DIR / f"{category}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _first_human_text(messages: list) -> str | None:
    for m in messages:
        if isinstance(m, HumanMessage):
            text = (m.content or "").strip() if isinstance(m.content, str) else str(m.content or "")
            if text:
                return text
    return None


def omit_old_tool_results(messages: list, *, keep: int = _TOOL_KEEP) -> list:
    """保留最近 keep 条 ToolMessage 原文；更早的只改 content，不删消息。"""
    tool_idxs = []
    for i, m in enumerate(messages):  # i 下标；m 本条消息
        if isinstance(m, ToolMessage):  # 是否工具返回
            tool_idxs.append(i)
    if len(tool_idxs) <= keep:
        return messages
    drop = set(tool_idxs[:-keep])
    out = []
    for i, m in enumerate(messages):
        if i in drop and isinstance(m, ToolMessage):
            out.append(
                ToolMessage(
                    content=_OMIT,
                    tool_call_id=getattr(m, "tool_call_id", "") or "",
                )
            )
        else:
            out.append(m)
    return out


def _count_for_summary(messages: list) -> int:
    return sum(
        1
        for m in messages
        if isinstance(m, (HumanMessage, AIMessage, ToolMessage))
    )


def summarize_if_long(
    messages: list,
    *,
    origin_user_text: str | None,
    user_id: int,
    ticket_id: int | None,
) -> list:
    """超过阈值：结构化摘要落库，中间历史换成一条摘要 SystemMessage。"""
    if _count_for_summary(messages) <= _SUMMARY_TRIGGER:
        return messages

    # 拼给便宜模型的素材（已占位化后的文本）
    lines = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue
        role = "user" if isinstance(m, HumanMessage) else (
            "tool" if isinstance(m, ToolMessage) else "assistant"
        )
        content = m.content if isinstance(m.content, str) else str(m.content or "")
        lines.append(f"{role}: {content[:300]}")
    blob = "\n".join(lines[-20:])

    try:
        from llm.client import model

        bound = model.with_structured_output(DialogSummary)
        result = bound.invoke(
            [
                SystemMessage(
                    content="把多轮工单对话压成一句中文摘要，保留用户初衷与已确认事实，不要编造。"
                ),
                HumanMessage(content=blob),
            ]
        )
        summary = (result.summary if isinstance(result, DialogSummary) else str(result)).strip()
    except Exception:
        summary = (origin_user_text or "用户咨询内部 IT 工单相关问题。").strip()

    if not summary:
        summary = origin_user_text or "（摘要为空）"

    save_chat_message(
        user_id=user_id,
        role="system",
        content=summary,
        kind="summary",
        ticket_id=ticket_id,
    )

    head: list = []
    # 保留开头的静态 system（人设），以及初衷 HumanMessage
    for m in messages:
        if isinstance(m, SystemMessage) and not (m.content or "").startswith("[对话摘要]"):
            head.append(m)
            if len(head) >= 1:
                break
    origin = None
    for m in messages:
        if isinstance(m, HumanMessage):
            text = (m.content or "").strip() if isinstance(m.content, str) else ""
            if origin_user_text and text == origin_user_text:
                origin = m
                break
            if origin is None:
                origin = m
                break
    tail = messages[-_KEEP_TAIL:]
    mid = [SystemMessage(content=f"[对话摘要] {summary}")]
    rebuilt = []
    seen = set()
    for m in [*head, *([origin] if origin else []), *mid, *tail]:
        if m is None:
            continue
        mid_id = id(m)
        if mid_id in seen and not isinstance(m, SystemMessage):
            continue
        seen.add(mid_id)
        rebuilt.append(m)
    return rebuilt


def compress_messages(
    messages: list,
    *,
    origin_user_text: str | None,
    user_id: int,
    ticket_id: int | None,
) -> list:
    """防爆管线：工具占位 →（可选）超长摘要。不改初衷句内容。"""
    stepped = omit_old_tool_results(messages, keep=_TOOL_KEEP)
    return summarize_if_long(
        stepped,
        origin_user_text=origin_user_text,
        user_id=user_id,
        ticket_id=ticket_id,
    )


def _db_rows_to_messages(rows: list[dict]) -> list:
    """full / summary 进模型；progress 已在查询时跳过。"""
    out = []
    for row in rows:
        kind = row.get("kind") or "full"
        if kind == "progress":
            continue
        role = row.get("role") or ""
        content = row.get("content") or ""
        if kind == "summary":
            out.append(SystemMessage(content=f"[对话摘要] {content}"))
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "system":
            out.append(SystemMessage(content=content))
    return out


def load_context(state: TicketAgentState) -> dict:
    """Skill 懒加载 + 读库（跳过 progress）+ 压缩管线。"""
    updates: dict = {}
    incoming = list(state.get("messages") or [])
    ticket_id = state.get("ticket_id")
    role = state.get("role") or ""
    user_id = int(state["user_id"])
    category = state.get("category")
    origin = state.get("origin_user_text")

    # 有工单：校验 + category
    if ticket_id is not None:
        with SyncSessionLocal() as db:
            ticket = db.execute(
                select(Ticket).where(Ticket.id == int(ticket_id))
            ).scalar_one_or_none()
        if ticket is None:
            return {
                "messages": [
                    *incoming,
                    SystemMessage(content=f"工单 #{ticket_id} 不存在，请换一个工单号。"),
                ]
            }
        if role == "employee" and ticket.user_id != user_id:
            return {
                "messages": [
                    *incoming,
                    SystemMessage(content="无权查看该工单，请只操作自己的单。"),
                ]
            }
        category = ticket.category
        updates["category"] = category

    # 库内历史：跳过 progress；若前端只带了很短一轮，用库补全
    db_rows = list_chat_messages(
        user_id=user_id,
        ticket_id=int(ticket_id) if ticket_id is not None else None,
        include_progress=False,
    )
    db_msgs = _db_rows_to_messages(db_rows)

    # 保留本轮前端传入的 system + 最新对话；库历史插在 system 后、本轮 user 前
    system_prefix = [m for m in incoming if isinstance(m, SystemMessage)][:1]
    non_system = [m for m in incoming if not isinstance(m, SystemMessage)]
    if db_msgs and len(non_system) <= 2:
        # 刷新续聊：库为主，再叠本轮最后一条 user（若有）
        merged = [*system_prefix, *db_msgs]
        if non_system:
            last = non_system[-1]
            if isinstance(last, HumanMessage):
                merged.append(last)
        messages = merged
    else:
        messages = list(incoming)

    if category:
        skill = _read_skill(str(category))
        if skill:
            messages = [
                *messages,
                SystemMessage(content=f"[本单 Skill / SOP]\n{skill}"),
            ]

    if not origin:
        origin = _first_human_text(messages)
        if origin:
            updates["origin_user_text"] = origin

    messages = compress_messages(
        messages,
        origin_user_text=origin or updates.get("origin_user_text"),
        user_id=user_id,
        ticket_id=int(ticket_id) if ticket_id is not None else None,
    )
    updates["messages"] = messages
    return updates


def save_turn(state: TicketAgentState) -> dict:
    """本轮有效 user / assistant 落库 kind=full。"""
    user_id = int(state["user_id"])
    ticket_id = state.get("ticket_id")
    tid = int(ticket_id) if ticket_id is not None else None
    messages = list(state.get("messages") or [])

    last_user = None
    last_ai = None
    for m in reversed(messages):
        if last_ai is None and isinstance(m, AIMessage):
            text = m.content if isinstance(m.content, str) else str(m.content or "")
            if text.strip() and not getattr(m, "tool_calls", None):
                last_ai = text.strip()
        if last_user is None and isinstance(m, HumanMessage):
            text = m.content if isinstance(m.content, str) else str(m.content or "")
            if text.strip():
                last_user = text.strip()
        if last_user and last_ai:
            break

    if last_user:
        save_chat_message(
            user_id=user_id, role="user", content=last_user, kind="full", ticket_id=tid
        )
    if last_ai:
        save_chat_message(
            user_id=user_id, role="assistant", content=last_ai, kind="full", ticket_id=tid
        )

    # 每轮可观测记账：工具名、检索条数、是否 HITL、粗算 token
    try:
        from agent.observability import persist_turn_metrics

        persist_turn_metrics(
            user_id=user_id,
            role=str(state.get("role") or ""),
            ticket_id=tid,
            messages=messages,
        )
    except Exception:
        pass
    return {}
