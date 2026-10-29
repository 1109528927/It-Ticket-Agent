# RAG 评测（第 1～4、6 步）

第 1～4 步锁语料、出题、标 GT、出标准集。第 6 步离线只评检索。  
当前锁定约 **39** 篇手册、标准集 **90** 题；扩库时 `lock_corpus_v1.py` 会复用旧 `doc_id`。

## 产物

| 路径 | 含义 |
|------|------|
| `corpus_v1/` | 锁定原文 + manifest |
| `queries_v1.jsonl` | 问句底稿（备份） |
| `queries_v1_gt.jsonl` | 标注复制件（`hint_doc_ids` = GT） |
| `dataset_v1.jsonl` | 标准评测集 |
| `run_retrieval_eval.py` | 离线检索评测 |
| `retrieval_eval_v1.jsonl` | 每题明细（跑完才有） |
| `retrieval_eval_v1.summary.json` | macro P/R/F1（跑完才有） |

## 标准评测集字段

```json
{
  "query_id": "q001",
  "query": "忘记域密码怎么办",
  "gt_doc_ids": ["doc_account_002"],
  "source": "doc_reverse",
  "difficulty": "easy",
  "category": "account"
}
```

## 第 6 步怎么跑

前提：Milvus 里已是与 `kb_source` 一致的手册向量（例如跑过 `srcipts/ingest_kb_md.py`），百炼 key 可用。

```bash
cd backend
PYTHONPATH=src .venv/bin/python eval/run_retrieval_eval.py --top-k 5
```

脚本做的事：读 `dataset_v1` → 每条调 `search_kb` → chunk.`source` 映射成 `doc_id` → 和 `gt_doc_ids` 算 P/R/F1 → 写明细和汇总。

## 其它命令

```bash
.venv/bin/python eval/lock_corpus_v1.py
.venv/bin/python eval/build_eval_dataset.py
.venv/bin/python eval/load_eval_dataset.py
```

---

# RAGAs v1（语义互补，非替换文档级 P/R）

依赖与主应用隔离：`.venv-ragas` + `requirements-ragas.txt`。指纹见 `RAGAS_LOCK.json`。

| 路径 | 含义 |
|------|------|
| `ragas_v1_seed.jsonl` | 30 条种子（问句 + ground_truth） |
| `build_ragas_v1.py` | 主 venv：同款 `search_kb` 填 contexts + 薄 LLM 填 answer |
| `ragas_v1_dataset.jsonl` | 组好的题（跑完 build 才有） |
| `run_ragas_eval.py` | `.venv-ragas`：中文裁判倾向 + 四指标 |
| `ragas_v1_scores.jsonl` / `ragas_v1_report.json` | 明细与宏平均 + 配置指纹 |
| `ragas_calib_template.md` | 人工归因表（每轮抽 5～10 条） |
| `smoke_ragas.py` | 1 条假数据冒烟 |

```bash
# 冒烟（RAGAs venv）
.venv-ragas/bin/python eval/smoke_ragas.py

# 组数据集（主应用 venv，需 Milvus + 百炼）
PYTHONPATH=src .venv/bin/python eval/build_ragas_v1.py

# 打分（RAGAs venv）
.venv-ragas/bin/python eval/run_ragas_eval.py
```

说明：薄封装生成 ≠ 线上 Agent；裁判与生成同模型时有自我偏好偏差；RAGAs Context P/R ≠ 文档级 doc_id P/R。
