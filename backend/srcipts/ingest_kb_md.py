#加载
from pathlib import Path
from pprint import pprint
from langchain_community.document_loaders import UnstructuredMarkdownLoader

KB_ROOT = Path(__file__).resolve().parent.parent / "kb_source"

docs = []
for path in sorted(KB_ROOT.rglob("*.md")):
    if path.name.upper() == "README.MD":
        continue  # 可选：跳过说明文件
    loader = UnstructuredMarkdownLoader(
        file_path=str(path),
        mode="single",
        strategy="fast",
    )
    docs.extend(loader.load())
    # 顺手把类别写进 metadata，后面检索可过滤
    for d in docs[-1:]:
        d.metadata["category"] = path.parent.name  # account/device/...

print("文件块数:", len(docs))
pprint(docs[0].metadata)
print(docs[0].page_content[:150], "...")


# 切分：得到加载数据后做切分；入参是 List[Document]，用 split_documents
from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=80,
    separators=[
        "\n## ",
        "\n### ",
        "\n\n",
        "\n",
        "。",
        " ",
        "",
    ],
)
chunks = text_splitter.split_documents(docs)

# print("切分后块数:", len(chunks))
# pprint(chunks[0].metadata)
# print(chunks[0].page_content[:200], "...")

# 嵌入：选型与初始化（项目用百炼 OpenAI 兼容，同聊天模型的 key / base_url）
import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

# OpenAIEmbeddings 的 chunk_size = 每次 API 最多几条文本（百炼 ≤10）
# 别和上面 RecursiveCharacterTextSplitter 的 chunk_size（每段多长）搞混
embed_model = OpenAIEmbeddings(
    model="text-embedding-v3",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    check_embedding_ctx_length=False,  # 百炼要字符串，关掉 tiktoken 预处理
    chunk_size=10,
)

# 向量化：对 chunks 做向量化，暂不写入向量库
texts = []
for c in chunks:  # 每次拿出一个 Document
    texts.append(c.page_content)

embeded_docs = embed_model.embed_documents(texts)
# embeded_docs[i] 对应 chunks[i] / texts[i]
print(
    "已向量化:",
    len(embeded_docs),
    "条；维度:",
    len(embeded_docs[0]) if embeded_docs else 0,
)


# ========== 手册有改动才跑本脚本：组装 Entity → 写入 ==========
# 日常聊天不跑上面 Load/切分/嵌入；只调 utils.milvus_kb.search_kb
import sys

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils import milvus_kb

data = []
for i in range(len(chunks)):
    data.append(
        {
            "id": i,
            "vector": embeded_docs[i],
            "text": chunks[i].page_content,
            "source": chunks[i].metadata.get("source"),
            "category": chunks[i].metadata.get("category"),
        }
    )
print("已组装 Entity:", len(data), "条")
if data:
    print("首条字段:", {k: (v if k != "vector" else f"<dim {len(v)}>") for k, v in data[0].items()})

insert_res = milvus_kb.upsert_entities(data)
print("insert result : ", insert_res)
stats = milvus_kb.get_client().get_collection_stats(
    collection_name=milvus_kb.COLLECTION
)
print("stats : ", stats)

# 写入后抽查检索（与助手将要调用的是同一个 search_kb）
hits = milvus_kb.search_kb("忘记域密码怎么办")
print("检索命中:", len(hits))
for h in hits:
    print(h)
