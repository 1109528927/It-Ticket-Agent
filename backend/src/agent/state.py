"""图状态。user_id / role 只由路由注入，不让模型改。"""

from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class TicketAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: int
    role: Literal["employee", "support"]
    ticket_id: NotRequired[int | None]
    category: NotRequired[str | None]
    origin_user_text: NotRequired[str | None]
