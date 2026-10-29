"""RAGAs 依赖冒烟：1～2 条假数据跑通 evaluate()，失败则勿批跑正式评测。

用法（RAGAs 专用 venv）：
  .venv-ragas/bin/python eval/smoke_ragas.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
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


def main() -> None:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY，无法冒烟")
    base = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    judge = os.getenv("RAGAS_JUDGE_MODEL", os.getenv("DASHSCOPE_MODEL", "qwen-plus"))
    embed = os.getenv("MILVUS_EMBED_MODEL", "text-embedding-v3")

    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=judge,
            api_key=api_key,
            base_url=base,
            temperature=0,
        )
    )
    emb = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=embed,
            api_key=api_key,
            base_url=base,
            check_embedding_ctx_length=False,
            chunk_size=10,
        )
    )

    rows = {
        "user_input": ["忘记域密码怎么办"],
        "response": [
            "应核实本人后提出重置密码，客服确认后生效；未确认前不能声称已重置成功。"
        ],
        "retrieved_contexts": [
            [
                "忘记域密码处理手册：提出重置密码须客服确认后才生效；未确认前一律未生效。"
            ]
        ],
        "reference": [
            "先核实报障人；提出重置密码写明工号；须客服确认后生效；未确认前不能声称已重置成功。"
        ],
    }
    ds = Dataset.from_dict(rows)
    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=emb,
    )
    print("smoke_ragas ok")
    print(result)
    return


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"smoke_ragas FAILED: {e}", file=sys.stderr)
        raise SystemExit(1) from e
