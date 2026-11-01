"""员工图：无高危工具；可写交接摘要。与客服图用数据库协作，不互调。"""

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.checkpointer import get_checkpointer
from agent.context import load_context, save_turn
from agent.prompts import SYSTEM_EMPLOYEE
from agent.state import TicketAgentState
from agent.tools.draft import TICKET_DRAFT_TOOLS
from agent.tools.handoff import HANDOFF_TOOLS
from agent.tools.tickets import SAFE_TOOLS
from llm.client import model

# 员工绝不 bind propose_xxx；可出工单预填草稿（不直接建单）
_EMPLOYEE_TOOLS = SAFE_TOOLS + HANDOFF_TOOLS + TICKET_DRAFT_TOOLS
_bound = model.bind_tools(_EMPLOYEE_TOOLS)

_graph = None


def agent(state: TicketAgentState) -> dict:
    messages = list(state["messages"])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_EMPLOYEE), *messages]
    response = _bound.invoke(messages)
    return {"messages": [response]}


def after_agent(state: TicketAgentState) -> Literal["safe_tools", "save_turn"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "safe_tools"
    return "save_turn"


def build_employee_graph():
    graph = StateGraph(TicketAgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("agent", agent)
    graph.add_node("safe_tools", ToolNode(_EMPLOYEE_TOOLS))
    graph.add_node("save_turn", save_turn)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges("agent", after_agent)
    graph.add_edge("safe_tools", "agent")
    graph.add_edge("save_turn", END)
    return graph.compile(checkpointer=get_checkpointer())


def get_employee_graph():
    global _graph
    if _graph is None:
        _graph = build_employee_graph()
    return _graph
