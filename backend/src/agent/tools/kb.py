"""知识库检索工具（客服侧）：混合检索 + 引用溯源；Milvus 挂了降级关键字。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from crud.kb_sync import search_kb_keyword
from utils import milvus_kb
from utils.retry import call_with_retry

logger = logging.getLogger(__name__)


def _format_hits(hits: list[dict], *, via: str) -> str:
    """统一引用格式，方便模型文末写「依据：[1]…」并带回 source。"""
    if not hits:
        return "知识库未检索到相关片段，请结合工单详情与 Skill 作答，勿编造步骤。勿伪造依据。"

    lines: list[str] = [f"检索通道={via}；作答时文末必须写「依据：[序号] source=…」，禁止无来源编造步骤。"]
    for i, h in enumerate(hits, 1):
        text = (h.get("text") or "").strip()
        if len(text) > 400:
            text = text[:400] + "…"
        source = h.get("source") or h.get("cite_id") or "unknown"
        cite_id = h.get("cite_id") or source
        chunk_id = h.get("id")
        cat = h.get("category") or ""
        head = f"[{i}] cite_id={cite_id} source={source}"
        if chunk_id is not None:
            head += f" chunk_id={chunk_id}"
        if cat:
            head += f" category={cat}"
        lines.append(f"{head}\n{text}")
    return "\n\n".join(lines)


def _search_with_fallback(q: str, category: str | None) -> str:
    try:
        hits = call_with_retry(
            milvus_kb.search_kb,
            q,
            limit=3,
            category=category,
            retries=1,
            label="search_kb.milvus",
        )
        # 给命中补 cite_id，便于溯源
        for h in hits:
            src = h.get("source") or f"chunk:{h.get('id')}"
            h["cite_id"] = src
        return _format_hits(hits, via="milvus_hybrid")
    except Exception as e:
        logger.exception("Milvus 检索失败，降级关键字 q=%s", q)
        try:
            hits = call_with_retry(
                search_kb_keyword,
                q,
                category=category,
                limit=3,
                retries=1,
                label="search_kb.keyword",
            )
            body = _format_hits(hits, via="keyword_fallback")
            return f"向量库暂不可用（{type(e).__name__}），已降级关键字检索。\n\n{body}"
        except Exception as e2:
            logger.exception("关键字降级也失败")
            return (
                f"知识库检索失败（向量：{e}；关键字：{e2}）。"
                "请结合工单详情与 Skill 作答，勿编造步骤，勿伪造依据。"
            )


@tool
def search_kb(q: str, category: str | None = None) -> str:
    """检索内部 IT 知识库（处理步骤、制度、手册）。问标准做法时先调用，不要瞎编 SOP。

    返回带 cite_id / source / chunk_id，作答须在文末写依据。

    Args:
        q: 用户问题或检索关键词。
        category: 可选，按类别过滤：account / device / network / permission。
    """
    return _search_with_fallback(q, category)


KB_TOOLS: list[Any] = [search_kb]
