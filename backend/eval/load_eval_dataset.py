"""读取标准评测集 dataset_v1.jsonl，供离线 Hit@K / Recall 等脚本直接调用。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_EVAL = Path(__file__).resolve().parent
DEFAULT_PATH = _EVAL / "dataset_v1.jsonl"
REQUIRED = ("query_id", "query", "gt_doc_ids")


def load_eval_dataset(path: str | Path | None = None) -> list[dict[str, Any]]:
    """返回 list[dict]，每条含 query_id / query / gt_doc_ids（及 source、difficulty、category）。"""
    p = Path(path) if path else DEFAULT_PATH
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        for key in REQUIRED:
            if key not in obj:
                raise ValueError(f"{p}:{i} 缺少字段 {key}")
        if not isinstance(obj["gt_doc_ids"], list) or not obj["gt_doc_ids"]:
            raise ValueError(f"{p}:{i} gt_doc_ids 须为非空 list")
        rows.append(obj)
    return rows


if __name__ == "__main__":
    data = load_eval_dataset()
    print(f"loaded {len(data)} from {DEFAULT_PATH.name}")
    print(json.dumps(data[0], ensure_ascii=False, indent=2))
