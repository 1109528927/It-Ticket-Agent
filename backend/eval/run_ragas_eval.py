"""跑 RAGAs v1：中文裁判倾向 + 四指标 + 配置指纹报告。

用【.venv-ragas】：
  .venv-ragas/bin/python eval/smoke_ragas.py   # 先冒烟
  .venv-ragas/bin/python eval/run_ragas_eval.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVAL = Path(__file__).resolve().parent
_BACKEND = _EVAL.parent

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env", override=True)

from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)


def _pkg_ver(name: str) -> str:
    try:
        import importlib.metadata as m

        return m.version(name)
    except Exception:
        return "unknown"


def _apply_chinese_prompts() -> None:
    """覆盖默认英文 instruction，降低中文场景切句/归因偏差（仍需人工校准）。"""
    faithfulness.nli_statements_prompt.instruction = (
        "你的任务是根据给定上下文，判断一系列陈述是否忠实。"
        "对每个陈述：若能由上下文直接推断则 verdict=1，否则 verdict=0。"
        "只依据上下文，不要使用外部知识。"
    )
    faithfulness.statement_generator_prompt.instruction = (
        "给定问题和答案，分析答案中每个句子的复杂度，"
        "将每个句子拆成一条或多条可独立理解的陈述，陈述中不要使用代词。"
        "用 JSON 输出。"
    )
    answer_relevancy.question_generation.instruction = (
        "根据给定答案生成一个问题，并判断答案是否含糊其辞。"
        "若答案回避、含糊或不确定（如「不知道」「不确定」），noncommittal=1，否则为 0。"
    )
    context_precision.context_precision_prompt.instruction = (
        "给定问题、答案与上下文，判断该上下文是否有助于得出该答案。"
        "有用则 verdict 为 1，否则为 0，并给出 JSON。"
    )
    context_recall.context_recall_prompt.instruction = (
        "给定上下文与参考答案，分析参考答案中的每一句能否归因于该上下文。"
        "能归因标 1，不能标 0，输出 JSON 并说明理由。"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=_EVAL / "ragas_v1_dataset.jsonl")
    parser.add_argument("--scores", type=Path, default=_EVAL / "ragas_v1_scores.jsonl")
    parser.add_argument("--report", type=Path, default=_EVAL / "ragas_v1_report.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--no-zh-prompt",
        action="store_true",
        help="不改中文裁判 instruction（用于对比实验）",
    )
    args = parser.parse_args()

    if not args.dataset.is_file():
        raise SystemExit(f"缺少数据集，请先跑 build_ragas_v1.py: {args.dataset}")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY")
    base = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    gen_model = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    judge_model = os.getenv("RAGAS_JUDGE_MODEL", gen_model)
    embed_model = os.getenv("MILVUS_EMBED_MODEL", "text-embedding-v3")
    same_model = judge_model == gen_model

    rows_raw = [
        json.loads(l)
        for l in args.dataset.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if args.limit and args.limit > 0:
        rows_raw = rows_raw[: args.limit]
    if not rows_raw:
        raise SystemExit("数据集为空")

    if not args.no_zh_prompt:
        _apply_chinese_prompts()

    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=judge_model,
            api_key=api_key,
            base_url=base,
            temperature=0,
        )
    )
    emb = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=embed_model,
            api_key=api_key,
            base_url=base,
            check_embedding_ctx_length=False,
            chunk_size=10,
        )
    )

    payload = {
        "user_input": [r["question"] for r in rows_raw],
        "response": [r.get("answer") or "" for r in rows_raw],
        "retrieved_contexts": [r.get("contexts") or [] for r in rows_raw],
        "reference": [r.get("ground_truth") or "" for r in rows_raw],
    }
    ds = Dataset.from_dict(payload)
    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=emb,
    )
    # ragas Result -> pandas / dict
    try:
        df = result.to_pandas()
    except Exception:
        df = None

    scores_out: list[dict] = []
    if df is not None:
        for i, row in enumerate(rows_raw):
            item = {
                "id": row.get("id"),
                "question": row.get("question"),
                "category": row.get("category"),
                "faithfulness": _num(df, i, "faithfulness"),
                "answer_relevancy": _num(df, i, "answer_relevancy"),
                "context_precision": _num(df, i, "context_precision"),
                "context_recall": _num(df, i, "context_recall"),
            }
            scores_out.append(item)

    args.scores.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in scores_out),
        encoding="utf-8",
    )

    metric_keys = (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    )
    macro: dict[str, float] = {}
    # 优先从逐条分数算 macro（Result 下标在部分 ragas 版本不可靠）
    for k in metric_keys:
        vals = [
            float(x[k])
            for x in scores_out
            if x.get(k) is not None
        ]
        if vals:
            macro[k] = round(sum(vals) / len(vals), 4)
    if not macro and hasattr(result, "__getitem__"):
        for k in metric_keys:
            try:
                macro[k] = round(float(result[k]), 4)
            except Exception:
                pass

    report = {
        "version": "ragas_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n": len(rows_raw),
        "sample_note": "默认约 30 条仅作整体趋势，不作分层归因结论；n 小则置信区间宽。",
        "macro": macro,
        "fingerprint": {
            "sample_file": args.dataset.name,
            "seed_file": "ragas_v1_seed.jsonl",
            "top_k": 3,
            "kb_hybrid": os.getenv("KB_HYBRID", "1"),
            "kb_rerank_min_score": os.getenv("KB_RERANK_MIN_SCORE", "0.22"),
            "kb_rerank_rel_ratio": os.getenv("KB_RERANK_REL_RATIO", "0.55"),
            "embed_model": embed_model,
            "gen_model": gen_model,
            "gen_prompt_version": rows_raw[0].get("prompt_version") or "thin_gen_v1",
            "judge_model": judge_model,
            "judge_same_as_gen": same_model,
            "zh_judge_prompt": not args.no_zh_prompt,
            "ragas": _pkg_ver("ragas"),
            "datasets": _pkg_ver("datasets"),
            "langchain-core": _pkg_ver("langchain-core"),
            "langchain-openai": _pkg_ver("langchain-openai"),
        },
        "bias_notes": [
            "薄封装生成答案通常比线上 Agent 更干净，Faithfulness/Answer Relevancy 可能偏高，不等价端到端。",
            (
                "裁判与生成同模型，存在自我偏好偏差，分数仅供趋势参考。"
                if same_model
                else "裁判与生成不同模型，已降低自我偏好风险。"
            ),
            "RAGAs Context P/R 与文档级 doc_id P/R 口径不同（排序平均精度 / claim 归因 ≠ ID 命中）。",
            "Faithfulness 高只说明答案可在 contexts 中找到依据，不证明依据文档本身正确。",
        ],
        "diagnosis_hints": {
            "doc_recall_high_context_low": "篇对了但块未盖住 claims，或裁判拆句偏差；先人工看。",
            "context_ok_faithfulness_low": "生成胡编或越权承诺。",
            "context_recall_low_faithfulness_high": "危险：证据缺失但生成自洽编圆；查漏检与胡编边界。",
            "answer_relevancy_low": "答非所问或跑题。",
        },
        "regression_gate": {
            "note": "相对基线任一核心指标下降超过 threshold 触发人工复核。",
            "relative_drop_threshold": 0.05,
            "baseline_report": "ragas_v1_report.baseline.json",
        },
        "calib_template": "ragas_calib_template.md",
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(macro, ensure_ascii=False, indent=2))
    print(f"scores → {args.scores}")
    print(f"report → {args.report}")


def _num(df, i: int, col: str) -> float | None:
    if col not in df.columns:
        return None
    try:
        v = df.iloc[i][col]
        if v is None or (isinstance(v, float) and v != v):
            return None
        return float(v)
    except Exception:
        return None


if __name__ == "__main__":
    main()
