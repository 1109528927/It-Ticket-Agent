"""高危工具：只提供 schema 给 bind_tools。禁止放进 ToolNode。

若误入执行器，只返回错误文案，绝不写库、不改密码。
真正写 pending 在图节点 propose_action。
"""

from typing import Any

from langchain_core.tools import tool

_BLOCK = "内部错误：高风险工具不可直接执行，须由 propose_action 节点处理。"


@tool
def propose_reset_password(
    ticket_id: int,
    reason: str,
    target_employee_no: str = "",
) -> str:
    """提出「重置密码」人工确认申请。不会立刻改密；客服须在处理页确认后才执行。

    Args:
        ticket_id: 工单编号（须为 processing 才可提出）。
        reason: 提出原因，不能为空。
        target_employee_no: 可选备注工号；改密对象以工单关联用户为准。

    Returns:
        提交结果说明（本函数体不应被 ToolNode 调用）。
    """
    _ = (ticket_id, reason, target_employee_no)
    return _BLOCK


@tool
def propose_change_permission(
    ticket_id: int,
    reason: str,
    permission_group: str = "",
) -> str:
    """提出「变更权限」人工确认申请。不会立刻改权限；客服须在处理页确认后才执行。

    Args:
        ticket_id: 工单编号（须为 processing 才可提出）。
        reason: 提出原因，不能为空。
        permission_group: 目标权限组备注。

    Returns:
        提交结果说明（本函数体不应被 ToolNode 调用）。
    """
    _ = (ticket_id, reason, permission_group)
    return _BLOCK


PROPOSE_TOOLS: list[Any] = [propose_reset_password, propose_change_permission]

# 高危名集合：route_tools / propose_action 共用
HIGH_RISK_TOOLS = frozenset(t.name for t in PROPOSE_TOOLS)
