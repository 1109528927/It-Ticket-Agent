"""客服图：只读进 ToolNode，高危只 bind。员工图：只读 + 交接 + 工单预填，无高危。"""

from agent.tools.draft import (
    REPLY_DRAFT_TOOLS,
    TICKET_DRAFT_TOOLS,
    prepare_reply_draft,
    prepare_ticket_draft,
)
from agent.tools.handoff import HANDOFF_TOOLS, write_handoff_summary
from agent.tools.kb import KB_TOOLS, search_kb
from agent.tools.propose import HIGH_RISK_TOOLS, PROPOSE_TOOLS, propose_change_permission, propose_reset_password
from agent.tools.tickets import SAFE_TOOLS, get_ticket, list_tickets

__all__ = [
    "SAFE_TOOLS",
    "KB_TOOLS",
    "PROPOSE_TOOLS",
    "HANDOFF_TOOLS",
    "TICKET_DRAFT_TOOLS",
    "REPLY_DRAFT_TOOLS",
    "HIGH_RISK_TOOLS",
    "list_tickets",
    "get_ticket",
    "search_kb",
    "write_handoff_summary",
    "prepare_ticket_draft",
    "prepare_reply_draft",
    "propose_reset_password",
    "propose_change_permission",
]
