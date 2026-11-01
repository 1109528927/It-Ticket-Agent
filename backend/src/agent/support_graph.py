"""客服图（Hub-and-spoke）：

外层仍与员工图隔离。内侧协作：
  load_context, ticket_brief, supervisor；
  escalate 走 escalate_reply 再 save_turn；
  resolve 走 resolver，与 safe_tools / propose_action 循环，再 guard, save_turn。

拆分理由：Supervisor 只路由；Resolver 持查单+检索全套工具连续完成；
Guard 为确定性质检。不为「功能名不同」再拆 Ticket/KB Agent。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from sqlalchemy import select

from agent.checkpointer import get_checkpointer
from agent.context import load_context, save_turn
from agent.prompts import SYSTEM_SUPERVISOR, SYSTEM_SUPPORT
from agent.state import TicketAgentState
from agent.tools.draft import REPLY_DRAFT_TOOLS
from agent.tools.kb import KB_TOOLS
from agent.tools.propose import HIGH_RISK_TOOLS, PROPOSE_TOOLS
from agent.tools.tickets import SAFE_TOOLS
from config.request import SyncSessionLocal
from crud.ticket_action_sync import propose_action_core
from llm.client import model
from model.ticket import Ticket

_FIXED_PENDING_MSG = "已提交人工确认，尚未执行。请等待客服在后台操作。"
_SUPPORT_SAFE = SAFE_TOOLS + KB_TOOLS + REPLY_DRAFT_TOOLS
_SUPPORT_BIND = _SUPPORT_SAFE + PROPOSE_TOOLS
_resolver_bound = model.bind_tools(_SUPPORT_BIND)

_PROPOSE_TYPE = {
    "propose_reset_password": "reset_password",
    "propose_change_permission": "change_permission",
}

# Guard：禁止嘴炮「已执行」
_FORBIDDEN_DONE = re.compile(
    r"(已重置成功|已经重置|密码已改好|已直接改好|已改好密码|"
    r"权限已变更成功|已经生效|已执行重置|已帮你改好)"
)
_MAX_GUARD_RETRY = 1

_graph = None


def _tool_call_name(call) -> str:
    if isinstance(call, dict):
        return call.get("name") or ""
    return getattr(call, "name", "") or ""


def _tool_call_id(call) -> str:
    if isinstance(call, dict):
        return call.get("id") or ""
    return getattr(call, "id", "") or ""


def _tool_call_args(call) -> dict:
    if isinstance(call, dict):
        return dict(call.get("args") or {})
    return dict(getattr(call, "args", None) or {})


def _message_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _last_human_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            return _message_text(m.content).strip()
    return ""


def _last_ai_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            return _message_text(m.content).strip()
    return ""


def _used_search_kb(messages: list) -> bool:
    for m in messages or []:
        if not isinstance(m, AIMessage):
            continue
        for c in getattr(m, "tool_calls", None) or []:
            if _tool_call_name(c) == "search_kb":
                return True
    return False


def ticket_brief(state: TicketAgentState) -> dict:
    """确定性节点：从库抽当前工单短摘要，供 Supervisor/Resolver 使用。"""
    tid = state.get("ticket_id")
    if not tid:
        return {"ticket_brief": None}
    try:
        tid_i = int(tid)
    except (TypeError, ValueError):
        return {"ticket_brief": None}

    brief = None
    try:
        with SyncSessionLocal() as db:
            row = db.execute(select(Ticket).where(Ticket.id == tid_i)).scalar_one_or_none()
            if row:
                brief = (
                    f"工单#{row.id} 标题={row.title or ''} 状态={row.status or ''} "
                    f"类别={row.category or ''} 优先级={row.priority or ''}"
                )
    except Exception:
        brief = f"工单#{tid_i}（摘要读取失败，请用工具查详情）"

    return {"ticket_brief": brief}


def supervisor(state: TicketAgentState) -> dict:
    """只路由：resolve | escalate。不调业务工具。"""
    user_q = _last_human_text(state.get("messages") or [])
    brief = (state.get("ticket_brief") or "").strip()
    user_blob = user_q or "（无用户原文）"
    if brief:
        user_blob = f"{user_blob}\n[关联工单摘要] {brief}"

    resp = model.invoke(
        [
            SystemMessage(content=SYSTEM_SUPERVISOR),
            HumanMessage(content=user_blob),
        ]
    )
    raw = _message_text(getattr(resp, "content", None)).strip()
    next_hop = "resolve"
    reason = "默认交 Resolver 处理"
    try:
        # 容忍前后杂讯，取第一段 {...}
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(raw[start : end + 1])
            n = str(obj.get("next") or "").strip().lower()
            if n in ("resolve", "escalate"):
                next_hop = n
            reason = str(obj.get("reason") or reason)[:80]
    except Exception:
        next_hop = "resolve"
        reason = "路由解析失败，交 Resolver"

    return {"route_to": next_hop, "route_reason": reason, "guard_fail_count": 0}


def after_supervisor(
    state: TicketAgentState,
) -> Literal["resolver", "escalate_reply"]:
    if (state.get("route_to") or "resolve") == "escalate":
        return "escalate_reply"
    return "resolver"


def escalate_reply(state: TicketAgentState) -> dict:
    reason = (state.get("route_reason") or "超出助手处理范围").strip()
    text = (
        f"该问题更适合转人工客服处理（{reason}）。"
        "请在工单台补充说明或联系值班客服；我这边不继续自动查库作答。"
    )
    return {"messages": [AIMessage(content=text)]}


def resolver(state: TicketAgentState) -> dict:
    """专家执行者：持有查单+检索+提案工具，在同一上下文连续完成。"""
    messages = list(state["messages"])
    sys0 = SYSTEM_SUPPORT
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=sys0), *messages]
    elif not (messages[0].content or "").startswith(
        "你是公司内部 IT 工单助手（客服侧·Resolver）"
    ):
        messages = [SystemMessage(content=sys0), *messages[1:]]

    brief = (state.get("ticket_brief") or "").strip()
    if brief:
        messages = [
            messages[0],
            SystemMessage(content=f"[当前工单摘要·代码生成]\n{brief}"),
            *messages[1:],
        ]

    response = _resolver_bound.invoke(messages)
    return {"messages": [response]}


def after_resolver(
    state: TicketAgentState,
) -> Literal["route_tools", "guard"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "route_tools"
    return "guard"


def route_tools(state: TicketAgentState) -> Command:
    """只做路由，不执行工具。高危去 propose_action，其余去 safe_tools。"""
    last = state["messages"][-1]
    calls = list(getattr(last, "tool_calls", None) or [])
    if not calls:
        return Command(goto="guard")

    names = [_tool_call_name(c) for c in calls]
    has_risk = any(n in HIGH_RISK_TOOLS for n in names)
    has_safe = any(n and n not in HIGH_RISK_TOOLS for n in names)
    if has_risk and has_safe:
        outs = [
            ToolMessage(
                content="请先查单或先提出，不要在同一轮混调；下一轮再单独调用。",
                tool_call_id=_tool_call_id(c),
            )
            for c in calls
        ]
        return Command(update={"messages": outs}, goto="resolver")

    if has_risk:
        return Command(goto="propose_action")
    return Command(goto="safe_tools")


def propose_action(state: TicketAgentState) -> dict:
    """手写节点：只调 sync propose，造 ToolMessage；绝不调改密码 API。"""
    last = state["messages"][-1]
    calls = list(getattr(last, "tool_calls", None) or [])
    outs: list[ToolMessage] = []
    support_id = int(state["user_id"])
    role = state.get("role") or ""
    state_ticket = state.get("ticket_id")

    for call in calls:
        name = _tool_call_name(call)
        call_id = _tool_call_id(call)
        if name not in HIGH_RISK_TOOLS:
            outs.append(
                ToolMessage(
                    content="此节点不处理该工具，请下一轮单独调用。",
                    tool_call_id=call_id,
                )
            )
            continue
        if role != "support":
            outs.append(
                ToolMessage(content="无权提出高风险动作。", tool_call_id=call_id)
            )
            continue

        args = _tool_call_args(call)
        ticket_id = state_ticket or args.get("ticket_id")
        try:
            ticket_id = int(ticket_id)
        except (TypeError, ValueError):
            outs.append(
                ToolMessage(
                    content="提出失败：缺少或非法 ticket_id。", tool_call_id=call_id
                )
            )
            continue

        reason = str(args.get("reason") or "").strip()
        action_type = _PROPOSE_TYPE[name]
        payload: dict = {}
        if action_type == "reset_password":
            no = str(args.get("target_employee_no") or "").strip()
            if no:
                payload["target_employee_no"] = no
        else:
            group = str(args.get("permission_group") or "").strip()
            if group:
                payload["permission_group"] = group

        code, data = propose_action_core(
            ticket_id=ticket_id,
            support_id=support_id,
            action_type=action_type,
            reason=reason,
            payload=payload or None,
        )
        if code != "ok":
            outs.append(
                ToolMessage(content=f"提出失败：{code}", tool_call_id=call_id)
            )
        else:
            action_id = (data or {}).get("action_id")
            outs.append(
                ToolMessage(
                    content=f"{_FIXED_PENDING_MSG} action_id={action_id}",
                    tool_call_id=call_id,
                )
            )

    return {"messages": outs}


def guard(state: TicketAgentState) -> Command:
    """确定性质检：禁嘴炮已执行；用过 search_kb 时要求有「依据」。"""
    text = _last_ai_text(state.get("messages") or [])
    fails: list[str] = []

    if text and _FORBIDDEN_DONE.search(text):
        fails.append("回复含「已执行/已改好」类表述，高危只能提案等人确认")

    if _used_search_kb(state.get("messages") or []) and text and "依据" not in text:
        fails.append("已调用 search_kb，文末须写「依据：[序号] source=…」")

    if not fails:
        return Command(goto="save_turn")

    count = int(state.get("guard_fail_count") or 0)
    if count >= _MAX_GUARD_RETRY:
        # 不再死循环：改写为安全收口
        safe = (
            "（质检未通过，已收口）请以工具结果为准："
            "高危操作须提出并等待人工确认；手册步骤请重新检索并标注依据。"
        )
        return Command(
            update={"messages": [AIMessage(content=safe)]},
            goto="save_turn",
        )

    tip = "；".join(fails)
    return Command(
        update={
            "guard_fail_count": count + 1,
            "messages": [
                SystemMessage(
                    content=(
                        f"[Guard 质检未通过] {tip}。"
                        "请修正后再答：禁止声称已改密/已改权限；"
                        "检索过则必须写依据。"
                    )
                )
            ],
        },
        goto="resolver",
    )


def build_support_graph():
    """编译客服图（可单例缓存）。"""
    graph = StateGraph(TicketAgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("ticket_brief", ticket_brief)
    graph.add_node("supervisor", supervisor)
    graph.add_node("escalate_reply", escalate_reply)
    graph.add_node("resolver", resolver)
    graph.add_node("route_tools", route_tools)
    graph.add_node("safe_tools", ToolNode(_SUPPORT_SAFE))
    graph.add_node("propose_action", propose_action)
    graph.add_node("guard", guard)
    graph.add_node("save_turn", save_turn)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "ticket_brief")
    graph.add_edge("ticket_brief", "supervisor")
    graph.add_conditional_edges("supervisor", after_supervisor)
    graph.add_edge("escalate_reply", "save_turn")
    graph.add_conditional_edges("resolver", after_resolver)
    graph.add_edge("safe_tools", "resolver")
    graph.add_edge("propose_action", "resolver")
    graph.add_edge("save_turn", END)
    return graph.compile(checkpointer=get_checkpointer())


def get_support_graph():
    global _graph
    if _graph is None:
        _graph = build_support_graph()
    return _graph
