"""知识库向量（给后端 / 助手调用）。

日常聊天只需要：连库 + 问题向量化 + search_kb，不要跑入库脚本整条龙。
手册有改动时，再跑 srcipts/ingest_kb_md.py（Load/切分/嵌入后调 upsert_entities）。

集合默认：库 rag_demo、集合 md（可用环境变量改）。
管理页文章同步未配 MILVUS_URI/HOST 时静默跳过。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MILVUS_URI = os.getenv("MILVUS_URI") or (
    f"http://{os.getenv('MILVUS_HOST', '127.0.0.1')}:{os.getenv('MILVUS_PORT', '19530')}"
    if os.getenv("MILVUS_HOST")
    else "http://127.0.0.1:19530"
)
DB_NAME = os.getenv("MILVUS_DB", "rag_demo")
COLLECTION = os.getenv("MILVUS_COLLECTION", "md")
EMBED_DIM = int(os.getenv("MILVUS_EMBED_DIM", "1024"))

# 兼容旧占位名
COLLECTION_NAME = COLLECTION

_client = None
_embed_model = None


def _sync_enabled() -> bool:
    """管理页文章同步：显式配置了 URI/HOST 才写向量，避免本地未起 Milvus 时拖垮保存。"""
    return bool(os.getenv("MILVUS_URI") or os.getenv("MILVUS_HOST"))


def get_client():
    """MilvusClient：建连并切到业务库。"""
    global _client
    if _client is not None:
        return _client
    from pymilvus import MilvusClient

    client = MilvusClient(MILVUS_URI)
    existed = client.list_databases()
    if DB_NAME not in existed:
        client.create_database(db_name=DB_NAME)
    client.use_database(db_name=DB_NAME)
    _client = client
    return _client


def get_embed_model():
    """与聊天共用百炼 key；入库和检索必须同一嵌入模型。"""
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    from langchain_openai import OpenAIEmbeddings

    _embed_model = OpenAIEmbeddings(
        model=os.getenv("MILVUS_EMBED_MODEL", "text-embedding-v3"),
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        check_embedding_ctx_length=False,
        chunk_size=10,
    )
    return _embed_model


def ensure_collection(*, dimension: int | None = None) -> None:
    """没有集合则创建。"""
    client = get_client()
    dim = dimension or EMBED_DIM
    if not client.has_collection(collection_name=COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            dimension=dim,
            metric_type="COSINE",
        )


def upsert_entities(data: list[dict[str, Any]]) -> dict:
    """写入已组装好的 Entity 列表，并 flush。"""
    client = get_client()
    ensure_collection()
    res = client.upsert(collection_name=COLLECTION, data=data)
    client.flush(collection_name=COLLECTION)
    return res if isinstance(res, dict) else {"result": res}


def search_kb(
    question: str,
    *,
    limit: int = 3,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """问题 → 同一 embed_model 向量化 → 指定集合相似度检索。

    返回精简命中列表，供助手工具或调试用：
    [{id, text, source, category, score}, ...]
    """
    client = get_client()
    embed_model = get_embed_model()
    query_vector = embed_model.embed_query(question)
    search_kwargs: dict[str, Any] = {
        "collection_name": COLLECTION,
        "data": [query_vector],
        "limit": limit,
        "output_fields": ["text", "source", "category", "id"],
    }
    if category:
        search_kwargs["filter"] = f'category == "{category}"'
    results = client.search(**search_kwargs)
    hits = results[0] if results else []
    out: list[dict[str, Any]] = []
    for h in hits:
        entity = h.get("entity") if isinstance(h, dict) else None
        if entity is None and isinstance(h, dict):
            # 部分版本字段摊平在 hit 上
            entity = h
        entity = entity or {}
        out.append(
            {
                "id": entity.get("id", h.get("id") if isinstance(h, dict) else None),
                "text": entity.get("text", ""),
                "source": entity.get("source"),
                "category": entity.get("category"),
                "score": h.get("distance") if isinstance(h, dict) else None,
            }
        )
    return out


def upsert_article(article_id: int, category: str, title: str, content: str) -> None:
    """MySQL 知识库文章保存时同步向量。未配 URI 时跳过（保留管理页可用）。"""
    if not _sync_enabled():
        logger.info("Milvus 未配置，跳过同步 article_id=%s", article_id)
        return
    try:
        embed_model = get_embed_model()
        text = f"{title}\n{content}".strip()
        vector = embed_model.embed_documents([text])[0]
        ensure_collection(dimension=len(vector))
        upsert_entities(
            [
                {
                    "id": int(article_id),
                    "vector": vector,
                    "text": text[:2000],
                    "source": f"kb_article:{article_id}",
                    "category": category,
                }
            ]
        )
    except Exception:
        logger.exception("Milvus 同步失败 article_id=%s", article_id)


def delete_article(article_id: int) -> None:
    if not _sync_enabled():
        logger.info("Milvus 未配置，跳过删除 article_id=%s", article_id)
        return
    try:
        client = get_client()
        if client.has_collection(collection_name=COLLECTION):
            client.delete(collection_name=COLLECTION, ids=[int(article_id)])
    except Exception:
        logger.exception("Milvus 删除失败 article_id=%s", article_id)
