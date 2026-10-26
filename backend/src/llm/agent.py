"""LangGraph Agent 入口：按 role 选图；SSE 推 status/token；灰字落 progress。"""

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.employee_graph import get_employee_graph
from agent.prompts import SYSTEM_EMPLOYEE, SYSTEM_SUPPORT
from agent.support_graph import get_support_graph
from config.request import DASHSCOPE_API_KEY
from crud.chat_sync import save_chat_message
from schema.ai import ChatRequest

_STATUS_BY_NODE = {
    "load_context": "正在装配上下文…",
    "route_tools": "正在路由工具…",
    "safe_tools": "正在查询…",
    "propose_action": "正在提交人工确认…",
    "save_turn": "正在保存对话…",
}


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


def run_agent(
    data: ChatRequest,
    *,
    user_id: int,
    role: str,
) -> str:
    if not DASHSCOPE_API_KEY:
        raise ValueError("no_key")

    graph, system, normalized_role = _pick_graph(role)
    result = graph.invoke(
        _initial_state(data, user_id=user_id, role=normalized_role, system=system),
        config={"recursion_limit": 25},
    )
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

        yield {"type": "status", "message": "正在生成…"}

        for mode, payload in graph.stream(
            state,
            stream_mode=["messages", "updates"],
            config={"recursion_limit": 25},
        ):
            if mode == "updates":
                if not isinstance(payload, dict):
                    continue
                for node_name in payload:
                    tip = _STATUS_BY_NODE.get(node_name)
                    if not tip:
                        continue
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
                continue

            if mode != "messages":
                continue

            chunk, meta = payload
            if meta.get("langgraph_node") != "agent":
                continue
            piece = _message_text(getattr(chunk, "content", None))
            if not piece:
                continue
            yield {"type": "token", "content": piece}

        yield {"type": "done"}
    except ValueError as exc:
        code = str(exc)
        if code == "empty":
            yield {"type": "error", "message": "请输入对话内容"}
        elif code == "no_key":
            yield {"type": "error", "message": "未配置大模型密钥"}
        elif code == "bad_role":
            yield {"type": "error", "message": "当前角色无法使用助手"}
        else:
            yield {"type": "error", "message": "大模型调用失败，请稍后重试"}
    except Exception:
        yield {"type": "error", "message": "大模型调用失败，请稍后重试"}
