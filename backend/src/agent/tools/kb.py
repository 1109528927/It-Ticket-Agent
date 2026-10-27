"""知识库检索工具（客服侧）：调 milvus_kb.search_kb（混合检索+重排），结果截断成短文本给模型。"""

from typing import Any

from langchain_core.tools import tool

from utils import milvus_kb


@tool
def search_kb(q: str, category: str | None = None) -> str:
    """检索内部 IT 知识库（处理步骤、制度、手册）。问标准做法时先调用，不要瞎编 SOP。

    底层：向量 + BM25 召回，RRF 融合，再重排后取 Top3。

    Args:
        q: 用户问题或检索关键词。
        category: 可选，按类别过滤：account / device / network / permission。
    """
    try:
        hits = milvus_kb.search_kb(q, limit=3, category=category)
    except Exception as e:
        return f"知识库检索失败：{e}"
    if not hits:
        return "知识库未检索到相关片段，请结合工单详情与 Skill 作答，勿编造步骤。"
    lines: list[str] = []
    for i, h in enumerate(hits, 1):
        text = (h.get("text") or "").strip()
        if len(text) > 400:
            text = text[:400] + "…"
        lines.append(
            f"[{i}] category={h.get('category')} source={h.get('source')}\n{text}"
        )
    return "\n\n".join(lines)


KB_TOOLS: list[Any] = [search_kb]
