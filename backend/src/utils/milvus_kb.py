"""知识库向量（给后端 / 助手调用）。

日常聊天只需要：连库 + 问题向量化 + search_kb，不要跑入库脚本整条龙。
手册有改动时，再跑 srcipts/ingest_kb_md.py（Load/切分/嵌入后调 upsert_entities）。

检索默认：向量召回 + BM25 召回 → RRF 融合 → 百炼文本重排，再截成 top limit。
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

# 混合检索 / 重排
KB_HYBRID = os.getenv("KB_HYBRID", "1") != "0"
KB_RERANK = os.getenv("KB_RERANK", "1") != "0"
KB_RECALL_LIMIT = int(os.getenv("KB_RECALL_LIMIT", "20"))
KB_RRF_K = int(os.getenv("KB_RRF_K", "60"))
KB_RERANK_MODEL = os.getenv("KB_RERANK_MODEL", "gte-rerank-v2")
KB_RERANK_URL = os.getenv(
    "KB_RERANK_URL",
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
)
# 重排截断：绝对下限 + 相对头名比例（任一满足可保留），避免多 GT 第二篇被砍光。0=关闭绝对阈值。
KB_RERANK_MIN_SCORE = float(os.getenv("KB_RERANK_MIN_SCORE", "0.22"))
KB_RERANK_REL_RATIO = float(os.getenv("KB_RERANK_REL_RATIO", "0.55"))

# 兼容旧占位名
COLLECTION_NAME = COLLECTION

_client = None
_embed_model = None
_bm25_index = None
_bm25_docs: list[dict[str, Any]] | None = None


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


def _invalidate_bm25() -> None:
    global _bm25_index, _bm25_docs
    _bm25_index = None
    _bm25_docs = None


def upsert_entities(data: list[dict[str, Any]]) -> dict:
    """写入已组装好的 Entity 列表，并 flush。"""
    client = get_client()
    ensure_collection()
    res = client.upsert(collection_name=COLLECTION, data=data)
    client.flush(collection_name=COLLECTION)
    _invalidate_bm25()
    return res if isinstance(res, dict) else {"result": res}


def _hit_to_doc(h: Any) -> dict[str, Any]:
    entity = h.get("entity") if isinstance(h, dict) else None
    if entity is None and isinstance(h, dict):
        entity = h
    entity = entity or {}
    return {
        "id": entity.get("id", h.get("id") if isinstance(h, dict) else None),
        "text": entity.get("text", ""),
        "source": entity.get("source"),
        "category": entity.get("category"),
        "score": h.get("distance") if isinstance(h, dict) else None,
    }


def _dense_search(
    question: str,
    *,
    limit: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
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
    return [_hit_to_doc(h) for h in hits]


def _tokenize(text: str) -> list[str]:
    import jieba

    return [t.strip() for t in jieba.lcut_for_search(text or "") if t and t.strip()]


def _ensure_bm25() -> None:
    """从 Milvus 拉全文，建内存 BM25（知识库体量小，够用）。"""
    global _bm25_index, _bm25_docs
    if _bm25_index is not None and _bm25_docs is not None:
        return
    from rank_bm25 import BM25Okapi

    client = get_client()
    if not client.has_collection(collection_name=COLLECTION):
        _bm25_docs = []
        _bm25_index = BM25Okapi([[]])
        return
    rows = client.query(
        collection_name=COLLECTION,
        filter="id >= 0",
        output_fields=["id", "text", "source", "category"],
        limit=16384,
    )
    _bm25_docs = list(rows or [])
    tokenized = [_tokenize(r.get("text") or "") for r in _bm25_docs]
    if not tokenized:
        tokenized = [[]]
    _bm25_index = BM25Okapi(tokenized)


def _bm25_search(
    question: str,
    *,
    limit: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
    _ensure_bm25()
    if not _bm25_docs or _bm25_index is None:
        return []
    scores = _bm25_index.get_scores(_tokenize(question))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for i, score in enumerate(scores):
        doc = _bm25_docs[i]
        if category and doc.get("category") != category:
            continue
        ranked.append((float(score), doc))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, doc in ranked[:limit]:
        out.append(
            {
                "id": doc.get("id"),
                "text": doc.get("text") or "",
                "source": doc.get("source"),
                "category": doc.get("category"),
                "score": score,
            }
        )
    return out


def _rrf_fuse(
    dense_hits: list[dict[str, Any]],
    bm25_hits: list[dict[str, Any]],
    *,
    k: int = KB_RRF_K,
) -> list[dict[str, Any]]:
    """倒数排名融合：score(d) = Σ 1/(k + rank)。"""
    scores: dict[Any, float] = {}
    docs: dict[Any, dict[str, Any]] = {}
    for rank, h in enumerate(dense_hits, 1):
        key = h.get("id")
        if key is None:
            continue
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
        docs[key] = h
    for rank, h in enumerate(bm25_hits, 1):
        key = h.get("id")
        if key is None:
            continue
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
        docs.setdefault(key, h)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{**docs[doc_id], "score": score} for doc_id, score in ordered]


def _dedupe_by_source(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一 source（同一篇）只留分最高的一块，减轻同文多块占坑。"""
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for h in hits:
        src = str(h.get("source") or h.get("id") or "")
        if src not in best:
            best[src] = h
            order.append(src)
            continue
        old = best[src].get("score")
        new = h.get("score")
        try:
            if new is not None and (old is None or float(new) > float(old)):
                best[src] = h
        except (TypeError, ValueError):
            pass
    return [best[s] for s in order]


def _cut_by_rerank_score(
    hits: list[dict[str, Any]],
    *,
    limit: int,
    min_score: float,
    rel_ratio: float = KB_RERANK_REL_RATIO,
) -> list[dict[str, Any]]:
    """按重排分截断弱相关。

    保留条件（有分数时）：s >= min_score，或 s >= 头名分 * rel_ratio。
    保证至少 1 条，最多 limit。min_score<=0 且 rel_ratio<=0 时不截断。
    """
    if not hits:
        return []
    if min_score <= 0 and rel_ratio <= 0:
        return hits[:limit]

    def _score_of(h: dict[str, Any]) -> float | None:
        score = h.get("score")
        try:
            return float(score) if score is not None else None
        except (TypeError, ValueError):
            return None

    top_s = None
    for h in hits:
        top_s = _score_of(h)
        if top_s is not None:
            break

    kept: list[dict[str, Any]] = []
    for h in hits:
        s = _score_of(h)
        if s is None:
            kept.append(h)
        else:
            ok_abs = min_score > 0 and s >= min_score
            ok_rel = (
                top_s is not None
                and rel_ratio > 0
                and s >= top_s * rel_ratio
            )
            if ok_abs or ok_rel:
                kept.append(h)
            elif kept:
                # 已有结果且后续掉出双阈值，后面更低，停止
                break
        if len(kept) >= limit:
            break
    if not kept:
        return hits[:1]
    return kept[:limit]


def _rerank(
    question: str,
    candidates: list[dict[str, Any]],
    *,
    top_n: int,
) -> list[dict[str, Any]]:
    """百炼文本重排；失败则退回 RRF 顺序。"""
    if not candidates or not KB_RERANK:
        return candidates[:top_n]
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.warning("未配置 DASHSCOPE_API_KEY，跳过重排")
        return candidates[:top_n]

    documents = [(c.get("text") or "")[:2000] for c in candidates]
    # 多要一些带分结果，便于后面按阈值截断
    ask_n = min(len(candidates), max(top_n * 3, top_n))
    try:
        import requests

        resp = requests.post(
            KB_RERANK_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": KB_RERANK_MODEL,
                "input": {"query": question, "documents": documents},
                "parameters": {"top_n": ask_n, "return_documents": False},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code"):
            raise RuntimeError(f"{data.get('code')}: {data.get('message')}")
        results = (data.get("output") or {}).get("results") or []
        out: list[dict[str, Any]] = []
        for r in results:
            idx = r.get("index")
            if idx is None or idx < 0 or idx >= len(candidates):
                continue
            item = dict(candidates[idx])
            item["score"] = r.get("relevance_score")
            out.append(item)
        ranked = out or candidates[:top_n]
        ranked = _dedupe_by_source(ranked)
        return _cut_by_rerank_score(
            ranked,
            limit=top_n,
            min_score=KB_RERANK_MIN_SCORE,
            rel_ratio=KB_RERANK_REL_RATIO,
        )
    except Exception:
        logger.exception("知识库重排失败，退回 RRF 顺序")
        return _dedupe_by_source(candidates)[:top_n]


def search_kb(
    question: str,
    *,
    limit: int = 3,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """混合检索：向量 + BM25 → RRF → 重排；返回 [{id, text, source, category, score}, ...]。

    KB_HYBRID=0 时退回纯向量；重排失败或 KB_RERANK=0 时按 RRF 截断。
    重排后按 KB_RERANK_MIN_SCORE 丢掉弱相关，并按 source 去重。
    """
    recall = max(limit, KB_RECALL_LIMIT)
    dense_hits = _dense_search(question, limit=recall, category=category)

    if not KB_HYBRID:
        return _dedupe_by_source(dense_hits)[:limit]

    try:
        bm25_hits = _bm25_search(question, limit=recall, category=category)
    except Exception:
        logger.exception("BM25 召回失败，退回纯向量")
        return _dedupe_by_source(dense_hits)[:limit]

    fused = _rrf_fuse(dense_hits, bm25_hits)
    if not fused:
        return _dedupe_by_source(dense_hits)[:limit]

    # 重排只看融合后的前 recall 条，省调用量
    return _rerank(question, fused[:recall], top_n=limit)


# 每篇文章最多 CHUNK_STRIDE 个块；id 落在 [article_id*STRIDE, (article_id+1)*STRIDE)
CHUNK_STRIDE = int(os.getenv("KB_CHUNK_STRIDE", "10000"))
CHUNK_SIZE = int(os.getenv("KB_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("KB_CHUNK_OVERLAP", "80"))
# 增量：只把变化块重新向量化；KB_INCREMENTAL=0 则整文重建
KB_INCREMENTAL = os.getenv("KB_INCREMENTAL", "1") != "0"


def article_chunk_id(article_id: int, chunk_idx: int) -> int:
    return int(article_id) * CHUNK_STRIDE + int(chunk_idx)


def _hash_chunk(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def _split_article_text(title: str, content: str) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    body = f"{title}\n{content}".strip()
    if not body:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", " ", ""],
    )
    chunks = splitter.split_text(body)
    return [c.strip() for c in chunks if c and c.strip()]


def _article_id_range(article_id: int) -> tuple[int, int]:
    start = int(article_id) * CHUNK_STRIDE
    return start, start + CHUNK_STRIDE


def _delete_article_vectors(article_id: int) -> None:
    """删旧单条 id，以及该文全部块 id。"""
    client = get_client()
    if not client.has_collection(collection_name=COLLECTION):
        return
    aid = int(article_id)
    start, end = _article_id_range(aid)
    try:
        client.delete(
            collection_name=COLLECTION,
            filter=f"id == {aid} or (id >= {start} and id < {end})",
        )
    except Exception:
        logger.exception("按 filter 删除向量失败，尝试按 id 列表 article_id=%s", aid)
        ids = [aid] + [start + i for i in range(min(256, CHUNK_STRIDE))]
        try:
            client.delete(collection_name=COLLECTION, ids=ids)
        except Exception:
            logger.exception("按 id 列表删除向量失败 article_id=%s", aid)


def _delete_vector_ids(ids: list[int]) -> None:
    if not ids:
        return
    client = get_client()
    # 分批，避免一次 id 过多
    batch = 128
    for i in range(0, len(ids), batch):
        chunk_ids = ids[i : i + batch]
        try:
            client.delete(collection_name=COLLECTION, ids=chunk_ids)
        except Exception:
            logger.exception("删除向量 id 失败 count=%s", len(chunk_ids))


def _query_article_chunks(article_id: int) -> list[dict[str, Any]]:
    """读出该文已有块（含 hash、向量），供增量比对。"""
    client = get_client()
    if not client.has_collection(collection_name=COLLECTION):
        return []
    start, end = _article_id_range(article_id)
    try:
        rows = client.query(
            collection_name=COLLECTION,
            filter=f"id >= {start} and id < {end}",
            output_fields=[
                "id",
                "text",
                "source",
                "category",
                "content_hash",
                "vector",
            ],
            limit=CHUNK_STRIDE,
        )
        return list(rows or [])
    except Exception:
        # 旧数据可能没有 content_hash / 取不到 vector
        logger.exception("查询文章块失败，尝试精简字段 article_id=%s", article_id)
        try:
            rows = client.query(
                collection_name=COLLECTION,
                filter=f"id >= {start} and id < {end}",
                output_fields=["id", "text", "source", "category"],
                limit=CHUNK_STRIDE,
            )
            return list(rows or [])
        except Exception:
            logger.exception("查询文章块再次失败 article_id=%s", article_id)
            return []


def _pick_free_slot(article_id: int, occupied: set[int]) -> int | None:
    start, end = _article_id_range(article_id)
    for mid in range(start, end):
        if mid not in occupied:
            return mid
    return None


def replace_article_chunks(
    article_id: int,
    category: str,
    title: str,
    content: str,
) -> dict[str, int]:
    """切分后同步向量。默认增量：没变的块复用，只嵌入变更/新增，删掉消失块。

    返回 {chunk_count, embedded, reused, deleted}；未配 Milvus 时全 0。
    """
    empty = {"chunk_count": 0, "embedded": 0, "reused": 0, "deleted": 0}
    if not _sync_enabled():
        logger.info("Milvus 未配置，跳过同步 article_id=%s", article_id)
        return empty

    chunks = _split_article_text(title, content)
    if not chunks:
        deleted_n = 0
        try:
            old = _query_article_chunks(article_id)
            ids = [int(r["id"]) for r in old if r.get("id") is not None]
            # 顺带清早期单条 id
            ids.append(int(article_id))
            _delete_vector_ids(ids)
            deleted_n = len(set(ids))
            _invalidate_bm25()
        except Exception:
            logger.exception("清空文章向量失败 article_id=%s", article_id)
            _delete_article_vectors(article_id)
        return {**empty, "deleted": deleted_n}

    if len(chunks) >= CHUNK_STRIDE:
        chunks = chunks[: CHUNK_STRIDE - 1]
        logger.warning("文章块数超限，已截断 article_id=%s", article_id)

    # 关闭增量：整文删除重建
    if not KB_INCREMENTAL:
        try:
            _delete_article_vectors(article_id)
            embed_model = get_embed_model()
            vectors = embed_model.embed_documents(chunks)
            ensure_collection(dimension=len(vectors[0]))
            data = []
            for i, (text, vector) in enumerate(zip(chunks, vectors)):
                data.append(
                    {
                        "id": article_chunk_id(article_id, i),
                        "vector": vector,
                        "text": text[:2000],
                        "source": f"kb_article:{article_id}#c{i}",
                        "category": category,
                        "content_hash": _hash_chunk(text),
                    }
                )
            upsert_entities(data)
            return {
                "chunk_count": len(data),
                "embedded": len(data),
                "reused": 0,
                "deleted": 0,
            }
        except Exception:
            logger.exception("Milvus 整文重建失败 article_id=%s", article_id)
            return empty

    try:
        old_rows = _query_article_chunks(article_id)
        # hash → 可复用实体队列（同文多块内容相同也按队列弹出）
        by_hash: dict[str, list[dict[str, Any]]] = {}
        for row in old_rows:
            text = row.get("text") or ""
            h = row.get("content_hash") or _hash_chunk(text)
            by_hash.setdefault(h, []).append(row)

        occupied: set[int] = set()
        reused_n = 0
        meta_upsert: list[dict[str, Any]] = []  # 内容没变、类别变了，只改元数据
        need_embed: list[str] = []

        for text in chunks:
            h = _hash_chunk(text)
            bucket = by_hash.get(h) or []
            if bucket and bucket[0].get("vector") is not None:
                row = bucket.pop(0)
                mid = int(row["id"])
                occupied.add(mid)
                reused_n += 1
                if row.get("category") != category:
                    meta_upsert.append(
                        {
                            "id": mid,
                            "vector": row["vector"],
                            "text": text[:2000],
                            "source": f"kb_article:{article_id}#h{h[:8]}",
                            "category": category,
                            "content_hash": h,
                        }
                    )
            else:
                if bucket:
                    bucket.pop(0)  # 有 hash 无向量，当新块嵌入
                need_embed.append(text)

        # 旧块里没被复用的 → 删除
        kept_ids = set(occupied)
        to_delete = [
            int(r["id"])
            for r in old_rows
            if r.get("id") is not None and int(r["id"]) not in kept_ids
        ]
        # 早期单条向量 id=article_id
        if int(article_id) not in kept_ids:
            to_delete.append(int(article_id))
        to_delete = list(dict.fromkeys(to_delete))
        _delete_vector_ids(to_delete)

        new_entities: list[dict[str, Any]] = []
        if need_embed:
            embed_model = get_embed_model()
            vectors = embed_model.embed_documents(need_embed)
            ensure_collection(dimension=len(vectors[0]))
            for text, vector in zip(need_embed, vectors):
                h = _hash_chunk(text)
                slot = _pick_free_slot(article_id, occupied)
                if slot is None:
                    logger.error("文章 %s 无空闲块位，跳过剩余嵌入", article_id)
                    break
                occupied.add(slot)
                new_entities.append(
                    {
                        "id": slot,
                        "vector": vector,
                        "text": text[:2000],
                        "source": f"kb_article:{article_id}#h{h[:8]}",
                        "category": category,
                        "content_hash": h,
                    }
                )

        upsert_payload = new_entities + meta_upsert
        if upsert_payload:
            ensure_collection(dimension=len(upsert_payload[0]["vector"]))
            upsert_entities(upsert_payload)
        elif to_delete:
            _invalidate_bm25()
        # 全无变化：不写库、不刷 BM25

        stats = {
            "chunk_count": reused_n + len(new_entities),
            "embedded": len(new_entities),
            "reused": reused_n,
            "deleted": len(to_delete),
        }
        logger.info(
            "增量同步 article_id=%s chunks=%s embedded=%s reused=%s deleted=%s",
            article_id,
            stats["chunk_count"],
            stats["embedded"],
            stats["reused"],
            stats["deleted"],
        )
        return stats
    except Exception:
        logger.exception("Milvus 增量同步失败，回退整文重建 article_id=%s", article_id)
        try:
            _delete_article_vectors(article_id)
            embed_model = get_embed_model()
            vectors = embed_model.embed_documents(chunks)
            ensure_collection(dimension=len(vectors[0]))
            data = []
            for i, (text, vector) in enumerate(zip(chunks, vectors)):
                data.append(
                    {
                        "id": article_chunk_id(article_id, i),
                        "vector": vector,
                        "text": text[:2000],
                        "source": f"kb_article:{article_id}#c{i}",
                        "category": category,
                        "content_hash": _hash_chunk(text),
                    }
                )
            upsert_entities(data)
            return {
                "chunk_count": len(data),
                "embedded": len(data),
                "reused": 0,
                "deleted": 0,
            }
        except Exception:
            logger.exception("Milvus 回退重建仍失败 article_id=%s", article_id)
            return empty


def upsert_article(article_id: int, category: str, title: str, content: str) -> None:
    """管理页保存：增量同步向量。"""
    replace_article_chunks(article_id, category, title, content)


def delete_article(article_id: int) -> None:
    if not _sync_enabled():
        logger.info("Milvus 未配置，跳过删除 article_id=%s", article_id)
        return
    try:
        _delete_article_vectors(article_id)
        _invalidate_bm25()
    except Exception:
        logger.exception("Milvus 删除失败 article_id=%s", article_id)
