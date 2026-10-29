"""第 6 步：离线检索评测（只评检索，不评生成）。

流程：
  读 dataset_v1 → 每条 query 调 search_kb 得 TopK chunk
  → source 映射成 doc_id → 与 gt_doc_ids 比 → Precision / Recall / F1

用法（在 backend 目录，需 Milvus + 百炼可用）：
  PYTHONPATH=src .venv/bin/python eval/run_retrieval_eval.py
  PYTHONPATH=src .venv/bin/python eval/run_retrieval_eval.py --top-k 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_EVAL = Path(__file__).resolve().parent
_BACKEND = _EVAL.parent
_SRC = _BACKEND / "src"
for p in (_SRC, _EVAL):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env", override=True)

from load_eval_dataset import load_eval_dataset  # noqa: E402

def _load_manifest(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def build_source_to_doc_id(manifest: list[dict]) -> dict[str, str]:
    """把 chunk.source（常见为 md 路径）映射到 doc_id。"""
    mapping: dict[str, str] = {}
    for m in manifest:
        doc_id = m["doc_id"]
        path_source = (m.get("path_source") or "").replace("\\", "/")
        path_locked = (m.get("path_locked") or "").replace("\\", "/")
        name = Path(path_source).name
        stem = Path(path_source).stem
        # 多种写法都能撞上
        for key in (
            path_source,
            path_locked,
            name,
            stem,
            f"kb_source/{path_source.split('kb_source/')[-1]}" if "kb_source/" in path_source else "",
        ):
            if key:
                mapping[key] = doc_id
                mapping[key.lower()] = doc_id
    return mapping


def chunk_to_doc_id(source: str | None, mapping: dict[str, str], manifest: list[dict]) -> str | None:
    if not source:
        return None
    s = str(source).replace("\\", "/")
    # 管理页同步：kb_article:12#c0 —— 本评测集按 md 入库时一般用不到
    if s.startswith("kb_article:"):
        return None
    if s in mapping:
        return mapping[s]
    if s.lower() in mapping:
        return mapping[s.lower()]
    name = Path(s).name
    if name in mapping:
        return mapping[name]
    stem = Path(s).stem
    if stem in mapping:
        return mapping[stem]
    # 路径后缀匹配 manifest
    for m in manifest:
        ps = (m.get("path_source") or "").replace("\\", "/")
        if ps and (s.endswith(ps) or s.endswith(Path(ps).name)):
            return m["doc_id"]
    return None


def prf(gt: set[str], pred: set[str]) -> tuple[float, float, float]:
    if not gt:
        return 0.0, 0.0, 0.0
    hit = len(gt & pred)
    precision = hit / len(pred) if pred else 0.0
    recall = hit / len(gt)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def main() -> None:
    parser = argparse.ArgumentParser(description="离线检索评测")
    parser.add_argument("--top-k", type=int, default=int(os.getenv("EVAL_TOP_K", "5")))
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_EVAL / "dataset_v1.jsonl",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_EVAL / "corpus_v1" / "manifest.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_EVAL / "retrieval_eval_v1.jsonl",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=_EVAL / "retrieval_eval_v1.summary.json",
    )
    parser.add_argument(
        "--filter-category",
        action="store_true",
        help="按题 category 过滤；若该题 gt_doc_ids 跨多类则自动不滤（避免跨类题漏检）",
    )
    args = parser.parse_args()

    from utils import milvus_kb

    rows = load_eval_dataset(args.dataset)
    manifest = _load_manifest(args.manifest)
    mapping = build_source_to_doc_id(manifest)
    doc_cat = {m["doc_id"]: m.get("category") for m in manifest}

    details: list[dict] = []
    sum_p = sum_r = sum_f = 0.0
    unmapped = 0
    skip_filter = 0

    for i, row in enumerate(rows, start=1):
        qid = row["query_id"]
        query = row["query"]
        gt = set(row["gt_doc_ids"])
        cat = (row.get("category") or "").strip() or None
        if not args.filter_category:
            cat = None
        else:
            gt_cats = {doc_cat.get(d) for d in gt if doc_cat.get(d)}
            if len(gt_cats) > 1:
                cat = None
                skip_filter += 1
        hits = milvus_kb.search_kb(query, limit=args.top_k, category=cat)
        pred: set[str] = set()
        chunk_sources: list[str] = []
        for h in hits:
            src = h.get("source")
            chunk_sources.append(str(src) if src is not None else "")
            doc_id = chunk_to_doc_id(src if isinstance(src, str) else None, mapping, manifest)
            if doc_id:
                pred.add(doc_id)
            else:
                unmapped += 1
        p, r, f1 = prf(gt, pred)
        sum_p += p
        sum_r += r
        sum_f += f1
        item = {
            "query_id": qid,
            "query": query,
            "gt_doc_ids": sorted(gt),
            "pred_doc_ids": sorted(pred),
            "hit_doc_ids": sorted(gt & pred),
            "chunk_sources": chunk_sources,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }
        details.append(item)
        print(
            f"[{i}/{len(rows)}] {qid} P={p:.2f} R={r:.2f} F1={f1:.2f} "
            f"gt={sorted(gt)} pred={sorted(pred)}"
        )

    n = len(rows) or 1
    summary = {
        "dataset": str(args.dataset.name),
        "top_k": args.top_k,
        "filter_category": bool(args.filter_category),
        "filter_category_skipped_cross": skip_filter,
        "kb_hybrid": os.getenv("KB_HYBRID", "1") != "0",
        "kb_rerank_min_score": float(os.getenv("KB_RERANK_MIN_SCORE", "0.22")),
        "kb_rerank_rel_ratio": float(os.getenv("KB_RERANK_REL_RATIO", "0.55")),
        "count": len(rows),
        "macro_precision": round(sum_p / n, 4),
        "macro_recall": round(sum_r / n, 4),
        "macro_f1": round(sum_f / n, 4),
        "unmapped_chunks": unmapped,
        "note": "文档级离线检索指标；Chunk→doc_id 依赖 source 与 manifest 对齐。",
    }
    args.out.write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in details),
        encoding="utf-8",
    )
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"明细: {args.out}")
    print(f"汇总: {args.summary}")


if __name__ == "__main__":
    main()
