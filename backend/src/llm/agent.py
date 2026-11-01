"""LangGraph Agent 入口：按 role 选图；SSE 推 status/token；灰字落 progress。"""

from collections.abc import Iterator
from typing import Any

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.checkpointer import make_thread_id
from agent.employee_graph import get_employee_graph
from agent.prompts import SYSTEM_EMPLOYEE, SYSTEM_SUPPORT
from agent.support_graph import get_support_graph
from config.request import DASHSCOPE_API_KEY
from crud.chat_sync import save_chat_message
from schema.ai import ChatRequest

_STATUS_BY_NODE = {
    "load_context": "正在装配上下文…",
    "ticket_brief": "正在读取工单摘要…",
    "supervisor": "正在路由（Supervisor）…",
    "escalate_reply": "建议转人工…",
    "resolver": "正在处理（Resolver）…",
    "agent": "正在生成…",
    "route_tools": "正在路由工具…",
    "safe_tools": "正在查询…",
    "propose_action": "正在提交人工确认…",
    "guard": "正在质检（Guard）…",
    "save_turn": "正在保存对话…",
}

_TICKET_DRAFT_RE = re.compile(r"TICKET_DRAFT_JSON:(\{.*\})\s*$", re.S)
_REPLY_DRAFT_RE = re.compile(r"REPLY_DRAFT_JSON:(\{.*\})\s*$", re.S)


def _draft_events_from_tool_messages(messages: list) -> list[dict]:
    """从 ToolMessage 里拆出工单预填 / 回复草稿事件给前端。"""
    events: list[dict] = []
    for m in messages or []:
        if not isinstance(m, ToolMessage):
            continue
        text = _message_text(m.content).strip()
        if not text:
            continue
        m_ticket = _TICKET_DRAFT_RE.search(text)
        if m_ticket:
            try:
                data = json.loads(m_ticket.group(1))
            except json.JSONDecodeError:
                continue
            events.append({"type": "ticket_draft", "draft": data})
            continue
        m_reply = _REPLY_DRAFT_RE.search(text)
        if m_reply:
            try:
                data = json.loads(m_reply.group(1))
            except json.JSONDecodeError:
                continue
            events.append(
                {
                    "type": "reply_draft",
                    "ticket_id": data.get("ticket_id"),
                    "content": data.get("content") or "",
                }
            )
    return events

# 只把「对用户可见的模型正文」打成 token；Supervisor JSON、工具节点不推
_TOKEN_NODES = frozenset({"agent", "resolver", "escalate_reply"})


def _build_history(data: ChatRequest, *, system: str) -> list:
    if not data.messages:
        raise ValueError("empty")
    history = [SystemMessage(content=system)]
    for message in data.messages:
        text = (message.content or "").strip()
        if message.role == "user" and text:
            history.append(HumanMessage(content=text))
        elif message.role == "assistant" and text:
            history.append(AIMessage(content=text))
    if len(history) <= 1:
        raise ValueError("empty")
    return history


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                texts.append(part.get("text") or "")
            else:
                texts.append(str(part))
        return "".join(texts)
    return str(content)


def _last_ai_text(messages: list) -> str:
    for message in reversed(messages or []):
        if isinstance(message, AIMessage):
            text = _message_text(message.content).strip()
            if text and not getattr(message, "tool_calls", None):
                return text
    return ""


def _pick_graph(role: str):
    if role == "employee":
        return get_employee_graph(), SYSTEM_EMPLOYEE, "employee"
    if role == "support":
        return get_support_graph(), SYSTEM_SUPPORT, "support"
    raise ValueError("bad_role")


def _initial_state(data: ChatRequest, *, user_id: int, role: str, system: str) -> dict:
    return {
        "messages": _build_history(data, system=system),
        "user_id": user_id,
        "role": role,
        "ticket_id": data.ticket_id,
    }


def _run_config(
    data: ChatRequest,
    *,
    user_id: int,
    role: str,
) -> tuple[dict, str]:
    thread_id = make_thread_id(
        user_id=user_id,
        role=role,
        ticket_id=data.ticket_id,
        client_thread_id=data.thread_id,
    )
    return (
        {
            "recursion_limit": 30,
            "configurable": {"thread_id": thread_id},
        },
        thread_id,
    )


def run_agent(
    data: ChatRequest,
    *,
    user_id: int,
    role: str,
) -> str:
    if not DASHSCOPE_API_KEY:
        raise ValueError("no_key")

    graph, system, normalized_role = _pick_graph(role)
    config, _thread_id = _run_config(data, user_id=user_id, role=normalized_role)
    try:
        result = graph.invoke(
            _initial_state(data, user_id=user_id, role=normalized_role, system=system),
            config=config,
        )
    except TimeoutError as e:
        raise ValueError("timeout") from e
    except Exception as e:
        name = type(e).__name__.lower()
        msg = str(e).lower()
        if "timeout" in name or "timeout" in msg or "timed out" in msg:
            raise ValueError("timeout") from e
        raise
    text = _last_ai_text(result.get("messages") or [])
    if not text:
        raise ValueError("empty_reply")
    return text


def stream_agent(
    data: ChatRequest,
    *,
    user_id: int,
    role: str,
) -> Iterator[dict]:
    try:
        if not DASHSCOPE_API_KEY:
            raise ValueError("no_key")

        graph, system, normalized_role = _pick_graph(role)
        state = _initial_state(
            data, user_id=user_id, role=normalized_role, system=system
        )
        ticket_id = data.ticket_id
        config, thread_id = _run_config(
            data, user_id=user_id, role=normalized_role
        )

        yield {"type": "status", "message": "正在生成…"}
        yield {"type": "thread", "thread_id": thread_id}

        for mode, payload in graph.stream(
            state,
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "updates":
                if not isinstance(payload, dict):
                    continue
                for node_name, update in payload.items():
                    tip = _STATUS_BY_NODE.get(node_name)
                    if tip:
                        # 出草稿时换一句更贴的灰字
                        if node_name == "safe_tools" and isinstance(update, dict):
                            draft_evs = _draft_events_from_tool_messages(
                                update.get("messages") or []
                            )
                            if any(e["type"] == "ticket_draft" for e in draft_evs):
                                tip = "正在生成工单预填…"
                            elif any(e["type"] == "reply_draft" for e in draft_evs):
                                tip = "正在生成回复草稿…"
                        yield {"type": "status", "message": tip}
                        # 灰字落库 progress，load_context 读库时会跳过
                        try:
                            save_chat_message(
                                user_id=user_id,
                                role="system",
                                content=tip,
                                kind="progress",
                                ticket_id=ticket_id,
                            )
                        except Exception:
                            pass
                    if node_name == "safe_tools" and isinstance(update, dict):
                        for ev in _draft_events_from_tool_messages(
                            update.get("messages") or []
                        ):
                            yield ev
                    # escalate / Guard 收口是整段 AIMessage，不会走模型流式
                    if node_name in ("escalate_reply", "guard") and isinstance(
                        update, dict
                    ):
                        for m in update.get("messages") or []:
                            if not isinstance(m, AIMessage):
                                continue
                            if getattr(m, "tool_calls", None):
                                continue
                            text = _message_text(m.content).strip()
                            if text:
                                yield {"type": "token", "content": text}
                continue

            if mode != "messages":
                continue

            chunk, meta = payload
            if meta.get("langgraph_node") not in _TOKEN_NODES:
                continue
            piece = _message_text(getattr(chunk, "content", None))
            if not piece:
                continue
            yield {"type": "token", "content": piece}

        yield {"type": "done", "thread_id": thread_id}
    except ValueError as exc:
        code = str(exc)
        if code == "empty":
            yield {"type": "error", "message": "请输入对话内容"}
        elif code == "no_key":
            yield {"type": "error", "message": "未配置大模型密钥"}
        elif code == "bad_role":
            yield {"type": "error", "message": "当前角色无法使用助手"}
        elif code == "timeout":
            yield {
                "type": "error",
                "message": "模型响应超时，请稍后重试或缩短问题后再问",
            }
        else:
            yield {"type": "error", "message": "大模型调用失败，请稍后重试"}
    except TimeoutError:
        yield {
            "type": "error",
            "message": "模型响应超时，请稍后重试或缩短问题后再问",
        }
    except Exception as exc:
        name = type(exc).__name__
        msg = str(exc).lower()
        if "timeout" in name.lower() or "timeout" in msg or "timed out" in msg:
            yield {
                "type": "error",
                "message": "模型响应超时，请稍后重试或缩短问题后再问",
            }
        else:
            yield {"type": "error", "message": "大模型调用失败，请稍后重试"}
