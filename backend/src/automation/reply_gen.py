"""为单张工单生成带依据的回复草稿（只起草，不发送、不执行高危）。"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.tools.kb import _search_with_fallback
from config.request import DASHSCOPE_API_KEY
from llm.client import model
from utils.retry import call_with_retry

_RISK_HINT = re.compile(
    r"(重置密码|改密|找回密码|权限组|开通权限|变更权限|删账号|禁用账号)",
    re.I,
)

_RISK_REASON_MAP = (
    ("重置密码|改密|找回密码", "涉及账号密码变更"),
    ("权限组|开通权限|变更权限", "涉及权限变更"),
    ("删账号|禁用账号", "涉及账号停用或删除"),
)


def looks_high_risk(text: str) -> bool:
    return bool(_RISK_HINT.search(text or ""))


def high_risk_reason_text(text: str) -> str:
    """给人看的高危原因摘要。"""
    raw = text or ""
    hit = []
    for pattern, label in _RISK_REASON_MAP:
        if re.search(pattern, raw, re.I):
            hit.append(label)
    if not hit:
        return "涉及需人工把关的敏感操作"
    # 去重保序
    seen = set()
    out = []
    for x in hit:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return "、".join(out)


def build_high_risk_user_notice(text: str) -> str:
    reason = high_risk_reason_text(text)
    return (
        f"您的工单已提交成功。"
        f"因{reason}，属于高风险事项，系统不会自动办结或改密改权，"
        f"将由客服在工作时间人工核实后再处理。"
        f"请留意本单时间线与客服回复；如有补充可在本单留言。"
    )


def create_success_message_for_user(*, title: str, description: str) -> tuple[str, bool]:
    """返回 (给员工的创建提示, 是否高危)。"""
    blob = f"{title}\n{description}"
    if not looks_high_risk(blob):
        return "创建成功", False
    reason = high_risk_reason_text(blob)
    return (
        f"创建成功。因{reason}，属高风险工单，需客服人工处理，"
        f"夜间也不会自动办结，请到工单详情查看说明与进度。",
        True,
    )

def generate_reply_draft_for_ticket(
    *,
    ticket_id: int,
    category: str,
    title: str,
    description: str,
    status: str,
) -> dict[str, Any]:
    """返回 {content, meta}。失败抛异常由上层记结果。"""
    if not DASHSCOPE_API_KEY:
        raise ValueError("no_key")

    q = f"{title}\n{description}".strip()
    kb_text = call_with_retry(
        _search_with_fallback,
        q[:500],
        category or None,
        retries=1,
        label="automation.search_kb",
    )

    risk = looks_high_risk(f"{title}\n{description}")
    risk_line = (
        "本单可能涉及高危（重置密码/改权限）：草稿中只能引导客服走提出+人审，"
        "禁止写「已重置成功/已改好」。"
        if risk
        else "本单未检出明显高危关键词；仍勿编造已执行结果。"
    )

    system = (
        "你是内部 IT 工单台的自动化起草助手。"
        "根据工单与知识库检索结果，写一版「客服可发给员工」的处理说明草稿。"
        "要求：简洁；步骤可执行；使用了检索则文末写「依据：[序号] source=…」；"
        "禁止声称已改密/已改权限；不要编造工单号。"
    )
    human = (
        f"工单#{ticket_id} 类别={category} 状态={status}\n"
        f"标题：{title}\n描述：{description}\n\n"
        f"{risk_line}\n\n知识库检索：\n{kb_text}\n\n请直接输出回复草稿正文。"
    )

    resp = call_with_retry(
        model.invoke,
        [SystemMessage(content=system), HumanMessage(content=human)],
        retries=1,
        label="automation.draft_llm",
    )
    content = (getattr(resp, "content", None) or str(resp)).strip()
    if not content:
        raise ValueError("empty_llm")

    meta = {
        "ticket_id": ticket_id,
        "category": category,
        "high_risk_hint": risk,
        "kb_preview": (kb_text or "")[:400],
    }
    return {"content": content, "meta": meta}
