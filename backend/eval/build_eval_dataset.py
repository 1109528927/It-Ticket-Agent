"""第 4 步：queries_v1_gt.jsonl → 标准评测集 dataset_v1.jsonl。

固定字段（每行一条 JSON）：
  query_id, query, gt_doc_ids, source, difficulty, category

用法（在 backend 目录）：
  .venv/bin/python eval/build_eval_dataset.py
"""

from __future__ import annotations

import json
from pathlib import Path

_EVAL = Path(__file__).resolve().parent
_SRC = _EVAL / "queries_v1_gt.jsonl"
_OUT = _EVAL / "dataset_v1.jsonl"
_META = _EVAL / "dataset_v1.meta.json"

# 标准评测集固定字段（读取代码只依赖这 6 个）
_FIELDS = ("query_id", "query", "gt_doc_ids", "source", "difficulty", "category")


def row_from_gt(raw: dict) -> dict:
    gt = list(raw.get("hint_doc_ids") or raw.get("gt_doc_ids") or [])
    if not raw.get("id") or not str(raw.get("query", "")).strip():
        raise ValueError(f"缺 id/query: {raw!r}")
    if not gt:
        raise ValueError(f"{raw.get('id')} 缺少 GT 文档 id")
    return {
        "query_id": raw["id"],
        "query": raw["query"].strip(),
        "gt_doc_ids": gt,
        "source": raw.get("source", ""),
        "difficulty": raw.get("difficulty", ""),
        "category": raw.get("category", ""),
    }


def build(src: Path = _SRC, out: Path = _OUT) -> list[dict]:
    rows: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(row_from_gt(json.loads(line)))
    out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    meta = {
        "version": "dataset_v1",
        "schema": list(_FIELDS),
        "path": out.name,
        "count": len(rows),
        "from": src.name,
        "note": "标准评测集：gt_doc_ids 为文档级金标准；用 load_eval_dataset 读取。",
    }
    _META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} rows={len(rows)}")
    return rows


if __name__ == "__main__":
    build()
