"""第 1 步延伸：用种子里的 question 跑检索，填上 contexts，写出 RAGAs 用 Dataset。

用法（在 backend 目录）：
  PYTHONPATH=src .venv/bin/python eval/build_ragas_dataset.py

输入：eval/ragas_seed.jsonl（人写 question + ground_truth）
输出：eval/ragas_dataset.jsonl（补齐 contexts；answer 仍空，留给跑助手）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=True)

from agent.tools.kb import _search_with_fallback  # noqa: E402

SEED = Path(__file__).resolve().parent / "ragas_seed.jsonl"
OUT = Path(__file__).resolve().parent / "ragas_dataset.jsonl"


def _contexts_from_tool_text(text: str) -> list[str]:
    """把 search_kb 返回拆成片段列表（按空行分块，去掉通道说明行）。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    # 第一段常是「检索通道=…」说明，留给 contexts 时去掉纯说明
    out: list[str] = []
    for p in parts:
        if p.startswith("检索通道=") or p.startswith("向量库暂不可用"):
            continue
        if "未检索到" in p or "检索失败" in p:
            continue
        out.append(p)
    return out


def main() -> None:
    if not SEED.is_file():
        raise SystemExit(f"缺少种子文件: {SEED}")

    rows_out: list[dict] = []
    with SEED.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            q = row["question"]
            cat = row.get("category")
            raw = _search_with_fallback(q, cat)
            contexts = _contexts_from_tool_text(raw)
            item = {
                "id": row.get("id"),
                "category": cat,
                "source_doc": row.get("source_doc"),
                "question": q,
                "ground_truth": row.get("ground_truth") or "",
                "contexts": contexts,
                "answer": row.get("answer") or "",
                "retrieval_raw_preview": raw[:500],
            }
            rows_out.append(item)
            print(
                f"{item['id']}: contexts={len(contexts)} "
                f"{'(空)' if not contexts else 'ok'}"
            )

    with OUT.open("w", encoding="utf-8") as f:
        for item in rows_out:
            # RAGAs 常用四字段；额外字段不影响手工查看
            slim = {
                "question": item["question"],
                "answer": item["answer"],
                "contexts": item["contexts"],
                "ground_truth": item["ground_truth"],
                "id": item["id"],
                "category": item["category"],
            }
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    print(f"已写入 {OUT} ，共 {len(rows_out)} 条")
    print("下一步：对每条跑助手填 answer，再交给 RAGAs 算指标。")


if __name__ == "__main__":
    main()
