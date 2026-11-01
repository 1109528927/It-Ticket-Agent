"""Agent 原生草稿：只产出结构化结果，不直接建单 / 不直接发回复。

- prepare_ticket_draft：员工侧，杂乱描述引导后的工单预填
- prepare_reply_draft：客服侧，带依据的回复草稿（处理页一键采用）
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

_CATEGORIES = frozenset({"account", "device", "network", "permission"})
_PRIORITIES = frozenset({"low", "medium", "high"})


@tool
def prepare_ticket_draft(
    title: str,
    category: str,
    description: str,
    priority: str = "medium",
    missing_info: str = "",
) -> str:
    """信息基本齐了再调用：生成结构化工单草稿。不会直接创建工单。

    员工须到「新建工单」页采用预填、可改字段后再提交。信息仍缺时先追问，不要急着调本工具。

    Args:
        title: 一句话标题，1～200 字。
        category: account / device / network / permission。
        description: 现象、时间、影响、已尝试步骤等完整描述。
        priority: low / medium / high，默认 medium。
        missing_info: 仍缺的信息；没有则空字符串。有缺项时仍可出草稿，但要在回复里提醒员工补全。
    """
    title = (title or "").strip()
    description = (description or "").strip()
    category = (category or "").strip().lower()
    priority = (priority or "medium").strip().lower()
    missing_info = (missing_info or "").strip()

    if not title or len(title) > 200:
        return "草稿失败：标题须 1～200 字，请改后再调。"
    if category not in _CATEGORIES:
        return (
            "草稿失败：category 只能是 account / device / network / permission。"
        )
    if not description:
        return "草稿失败：描述不能为空，请先追问补全再调。"
    if priority not in _PRIORITIES:
        return "草稿失败：priority 只能是 low / medium / high。"

    payload = {
        "category": category,
        "title": title,
        "description": description,
        "priority": priority,
        "missing_info": missing_info,
    }
    miss = missing_info or "无"
    return (
        "已生成工单草稿（尚未建单）。"
        "请员工在助手页核对后点「确认建单」；也可去新建页采用预填再改。\n"
        f"缺项：{miss}\n"
        f"TICKET_DRAFT_JSON:{json.dumps(payload, ensure_ascii=False)}"
    )


@tool
def prepare_reply_draft(
    reply_body: str,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """把「写给员工的处理说明」落成处理页可一键采用的回复草稿。须已关联工单。

    手册/步骤类回复正文须含「依据」；本工具不直接发送回复。

    Args:
        reply_body: 可直接发给员工的正文（可含文末依据）。
    """
    body = (reply_body or "").strip()
    if not body:
        return "草稿失败：回复正文不能为空。"
    if len(body) > 2000:
        return "草稿失败：回复超过 2000 字，请缩短后再调。"

    ticket_id = (state or {}).get("ticket_id")
    if ticket_id is None:
        return "草稿失败：请先在助手页关联工单，再生成回复草稿。"

    try:
        tid = int(ticket_id)
    except (TypeError, ValueError):
        return "草稿失败：工单号无效。"

    tip = ""
    if "依据" not in body:
        tip = "（提示：正文未写「依据」，若用过手册检索请补上后再给客服采用。）\n"

    payload = {"ticket_id": tid, "content": body}
    return (
        f"{tip}已生成回复草稿（尚未发送）。"
        "请到该单处理页点「采用助手草稿」，核对后发送。\n"
        f"REPLY_DRAFT_JSON:{json.dumps(payload, ensure_ascii=False)}"
    )


TICKET_DRAFT_TOOLS: list[Any] = [prepare_ticket_draft]
REPLY_DRAFT_TOOLS: list[Any] = [prepare_reply_draft]
