"""绑定通义千问。还没有 Schema、还没有对话路由。"""

from langchain.chat_models import init_chat_model

from config.request import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL

# streaming=True：SSE 打字机需要；不影响 invoke
model = init_chat_model(
    model=LLM_MODEL,
    model_provider="openai",
    api_key=DASHSCOPE_API_KEY or "missing",
    base_url=DASHSCOPE_BASE_URL,
    streaming=True,
)


def ping() -> str:
    """发一句固定的话，看模型有没有回复。不通就先别写 Schema。"""
    if not DASHSCOPE_API_KEY:
        raise ValueError("no_key")
    res = model.invoke("用一句话介绍你自己")
    content = getattr(res, "content", None) or str(res)
    return str(content).strip()
