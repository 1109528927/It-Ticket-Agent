"""组 RAGAs v1 数据集：同款 search_kb 填 contexts + 薄 LLM 填 answer。

用【主应用 venv】跑（需 Milvus + 百炼），不要用 .venv-ragas。

用法：
  PYTHONPATH=src .venv/bin/python eval/build_ragas_v1.py
  PYTHONPATH=src .venv/bin/python eval/build_ragas_v1.py --limit 5
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
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env", override=True)

SEED = _EVAL / "ragas_v1_seed.jsonl"
OUT = _EVAL / "ragas_v1_dataset.jsonl"
PROMPT_VERSION = "thin_gen_v2"


def _gen_answer(question: str, contexts: list[str]) -> str:
    from openai import OpenAI

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY")
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )
    model = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    ctx_block = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1)) or "（无检索上下文）"
    messages = [
        {
            "role": "system",
            "content": (
                "你是内部 IT 客服助手的离线评测生成器，目标是忠实于上下文，不是写长客服话术。"
                "只复述或改写上下文里已有的检查项、制度与升级条件；上下文没有的路径、菜单、端口、错误码、品牌步骤一律不要写。"
                "回答尽量短：通常 5～8 句或等价短列表即可，不要寒暄堆砌、不要展开成教程。"
                "涉及重置密码、变更权限时，必须说明须提出并经客服确认后才生效，禁止声称已直接改好。"
                "若上下文不足，只写「上下文未写明，需补充信息或转人工」，不要用常识补全。"
                "文末用「依据：[序号]」标注用到的上下文。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"问题：{question}\n\n上下文：\n{ctx_block}\n\n"
                "请严格按上下文作答，禁止补充上下文没有的操作细节："
            ),
        },
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=450,
    )
    return (resp.choices[0].message.content or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条，0=全部")
    parser.add_argument("--seed", type=Path, default=SEED)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    from utils import milvus_kb

    rows = [
        json.loads(l)
        for l in args.seed.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out: list[dict] = []
    for i, row in enumerate(rows, 1):
        q = row["question"]
        cat = row.get("category")
        hits = milvus_kb.search_kb(q, limit=3, category=cat)
        contexts = [
            (h.get("text") or "").strip()
            for h in hits
            if (h.get("text") or "").strip()
        ]
        answer = _gen_answer(q, contexts)
        item = {
            "id": row.get("id"),
            "question": q,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": row.get("ground_truth") or "",
            "category": cat,
            "difficulty": row.get("difficulty"),
            "gt_doc_ids": row.get("gt_doc_ids") or [],
            "prompt_version": PROMPT_VERSION,
            "gen_model": os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
            "hit_sources": [h.get("source") for h in hits],
        }
        out.append(item)
        print(f"[{i}/{len(rows)}] {item['id']} contexts={len(contexts)} answer_len={len(answer)}")

    args.out.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out),
        encoding="utf-8",
    )
    print(f"wrote {args.out} n={len(out)}")
    print("说明：薄封装生成，分数不直接等价线上 Agent 端到端。")


if __name__ == "__main__":
    main()
