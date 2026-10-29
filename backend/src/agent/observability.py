"""每轮 Agent 可观测汇总：工具名、检索条数、是否 HITL、粗算 token。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)

_HITL_TOOLS = frozenset({"propose_reset_password", "propose_change_permission"})
_KB_HIT_LINE = re.compile(r"^\[\d+\]", re.MULTILINE)


def _tool_call_name(tc: Any) -> str | None:
    if isinstance(tc, dict):
        name = tc.get("name")
    else:
        name = getattr(tc, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _usage_from_ai(message: AIMessage) -> tuple[int, int]:
    """从单条 AIMessage 抽 input/output token；没有则 0。"""
    um = getattr(message, "usage_metadata", None) or {}
    if isinstance(um, dict):
        inp = um.get("input_tokens") or um.get("prompt_tokens") or 0
        out = um.get("output_tokens") or um.get("completion_tokens") or 0
        try:
            return int(inp or 0), int(out or 0)
        except (TypeError, ValueError):
            pass

    meta = getattr(message, "response_metadata", None) or {}
    if isinstance(meta, dict):
        tu = meta.get("token_usage") or meta.get("usage") or {}
        if isinstance(tu, dict):
            try:
                return int(tu.get("prompt_tokens") or tu.get("input_tokens") or 0), int(
                    tu.get("completion_tokens") or tu.get("output_tokens") or 0
                )
            except (TypeError, ValueError):
                return 0, 0
    return 0, 0


def _kb_hits_from_tool_content(text: str) -> int:
    if not text:
        return 0
    if "未检索到" in text or "检索失败" in text:
        return 0
    return len(_KB_HIT_LINE.findall(text))


def collect_turn_metrics(messages: list) -> dict[str, Any]:
    """从本轮最后一条用户消息起汇总。返回可直接落库的字段。"""
    if not messages:
        return {
            "tools": [],
            "kb_hit_count": 0,
            "hitl": False,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    start = 0
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            start = i

    segment = messages[start:]
    tools: list[str] = []
    kb_hit_count = 0
    input_tokens = 0
    output_tokens = 0

    for m in segment:
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", None) or []:
                name = _tool_call_name(tc)
                if name:
                    tools.append(name)
            inp, out = _usage_from_ai(m)
            input_tokens += inp
            output_tokens += out
        elif isinstance(m, ToolMessage):
            name = getattr(m, "name", None) or ""
            text = _message_text(m.content)
            if name == "search_kb" or (not name and ("category=" in text or "知识库" in text)):
                kb_hit_count += _kb_hits_from_tool_content(text)

    # 去重但保序（同轮多次 search_kb 都保留在列表里更利于回放）
    hitl = any(t in _HITL_TOOLS for t in tools)
    return {
        "tools": tools,
        "kb_hit_count": kb_hit_count,
        "hitl": hitl,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def persist_turn_metrics(
    *,
    user_id: int,
    role: str,
    ticket_id: int | None,
    messages: list,
) -> dict[str, Any] | None:
    """汇总并写入 agent_turn_log；失败只打日志，不挡主流程。"""
    metrics = collect_turn_metrics(messages)
    payload = {
        "user_id": user_id,
        "ticket_id": ticket_id,
        "role": role,
        "tools": metrics["tools"],
        "kb_hit_count": metrics["kb_hit_count"],
        "hitl": metrics["hitl"],
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
    }
    logger.info(
        "agent_turn %s",
        json.dumps(payload, ensure_ascii=False),
    )
    try:
        from crud.agent_turn_sync import save_agent_turn_log

        save_agent_turn_log(
            user_id=user_id,
            role=role,
            ticket_id=ticket_id,
            tools=metrics["tools"],
            kb_hit_count=metrics["kb_hit_count"],
            hitl=metrics["hitl"],
            input_tokens=metrics["input_tokens"],
            output_tokens=metrics["output_tokens"],
        )
    except Exception:
        logger.exception("写入 agent_turn_log 失败 user_id=%s", user_id)
    return metrics
