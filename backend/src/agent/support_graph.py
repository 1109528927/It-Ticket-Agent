"""客服图：load_context → agent → route_tools → safe_tools | propose_action。

高危名只 bind schema，绝不进 ToolNode。提出只走 propose_action + sync CRUD。
"""

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from agent.context import load_context, save_turn
from agent.prompts import SYSTEM_SUPPORT
from agent.state import TicketAgentState
from agent.tools.kb import KB_TOOLS
from agent.tools.propose import HIGH_RISK_TOOLS, PROPOSE_TOOLS
from agent.tools.tickets import SAFE_TOOLS
from crud.ticket_action_sync import propose_action_core
from llm.client import model

_FIXED_PENDING_MSG = "已提交人工确认，尚未执行。请等待客服在后台操作。"
# 客服只读：查单 + 知识库；员工图仍只用 SAFE_TOOLS，不挂 search_kb
_SUPPORT_SAFE = SAFE_TOOLS + KB_TOOLS
_SUPPORT_BIND = _SUPPORT_SAFE + PROPOSE_TOOLS
_bound = model.bind_tools(_SUPPORT_BIND)

_PROPOSE_TYPE = {
    "propose_reset_password": "reset_password",
    "propose_change_permission": "change_permission",
}

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


def agent(state: TicketAgentState) -> dict:
    """调用绑定了工具的大模型。"""
    messages = list(state["messages"])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_SUPPORT), *messages]
    response = _bound.invoke(messages)
    return {"messages": [response]}


def after_agent(state: TicketAgentState) -> Literal["route_tools", "save_turn"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "route_tools"
    return "save_turn"


def route_tools(state: TicketAgentState) -> Command:
    """只做路由，不执行工具。高危去 propose_action，其余去 safe_tools。"""
    last = state["messages"][-1]
    calls = list(getattr(last, "tool_calls", None) or [])
    if not calls:
        return Command(goto="save_turn")

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
        return Command(update={"messages": outs}, goto="agent")

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
                ToolMessage(content="提出失败：缺少或非法 ticket_id。", tool_call_id=call_id)
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


def build_support_graph():
    """编译客服图（可单例缓存）。"""
    graph = StateGraph(TicketAgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("agent", agent)
    graph.add_node("route_tools", route_tools)
    graph.add_node("safe_tools", ToolNode(_SUPPORT_SAFE))
    graph.add_node("propose_action", propose_action)
    graph.add_node("save_turn", save_turn)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges("agent", after_agent)
    graph.add_edge("safe_tools", "agent")
    graph.add_edge("propose_action", "agent")
    graph.add_edge("save_turn", END)
    return graph.compile()


def get_support_graph():
    global _graph
    if _graph is None:
        _graph = build_support_graph()
    return _graph
