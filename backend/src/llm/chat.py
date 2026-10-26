"""整包对话：拼接消息并返回模型最新回复。还不走 LangGraph。"""

from config.request import DASHSCOPE_API_KEY
from llm.client import model
from schema.ai import ChatRequest

SYSTEM_PROMPT = """你是内部 IT 工单台助手，回答要简洁。
你目前还查不到真实工单和知识库，不要编造单号、状态或处理结果。
用户问具体工单或步骤时，请说明去工单页或知识库页查看，或等助手工具接上后再问。
与工单、账号、设备、网络、权限无关的问题，直接说明你只回答内部 IT 报障相关问题。
"""


def chat(data: ChatRequest) -> str:
    """返回模型回复文本。失败抛 ValueError，路由再转 HTTPException。"""
    if not DASHSCOPE_API_KEY:
        raise ValueError("no_key")
    if not data.messages:
        raise ValueError("empty")

    history = []
    for message in data.messages:
        text = (message.content or "").strip()
        if message.role in ("user", "assistant") and text:
            history.append({"role": message.role, "content": text})
    if not history:
        raise ValueError("empty")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)

    res = model.invoke(messages)
    content = getattr(res, "content", None) or ""
    if not str(content).strip():
        raise ValueError("empty_reply")
    return str(content).strip()
