import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from crud.chat_sync import list_chat_messages
from llm.agent import run_agent, stream_agent
from llm.chat import chat
from model.user import User
from schema.ai import ChatMessage, ChatRequest
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(tags=["ai"])


def _map_llm_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "no_key":
        return HTTPException(status_code=500, detail="未配置大模型密钥")
    if code == "empty":
        return HTTPException(status_code=400, detail="请输入对话内容")
    if code == "empty_reply":
        return HTTPException(status_code=502, detail="大模型没有返回内容")
    if code == "bad_role":
        return HTTPException(status_code=403, detail="当前角色无法使用助手")
    if code == "timeout":
        return HTTPException(
            status_code=504, detail="模型响应超时，请稍后重试或缩短问题后再问"
        )
    return HTTPException(status_code=502, detail="大模型调用失败，请稍后重试")


def _sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream_response(body: ChatRequest, user: User) -> StreamingResponse:
    def event_gen():
        for event in stream_agent(body, user_id=user.id, role=user.role):
            yield _sse_line(event)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/ai/chat")
async def chat_api(
    body: ChatRequest,
    user: User = Depends(get_current_user),
):
    """整包 chat（不通图，调试用）。"""
    _ = user
    try:
        content = await asyncio.to_thread(chat, body)
    except ValueError as exc:
        raise _map_llm_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="大模型调用失败，请稍后重试") from exc

    data = ChatMessage(role="assistant", content=content).model_dump()
    return success_response(message="ok", data=data)


@router.post("/api/ai/agent")
async def agent_api(
    body: ChatRequest,
    user: User = Depends(get_current_user),
):
    """业务图整包返回（调试用）。"""
    try:
        content = await asyncio.to_thread(
            run_agent,
            body,
            user_id=user.id,
            role=user.role,
        )
    except ValueError as exc:
        raise _map_llm_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="大模型调用失败，请稍后重试") from exc

    data = ChatMessage(role="assistant", content=content).model_dump()
    return success_response(message="ok", data=data)


@router.post("/api/ai/chat/stream")
async def chat_stream_api(
    body: ChatRequest,
    user: User = Depends(get_current_user),
):
    """主路径 SSE：按 role 跑业务图。"""
    return _stream_response(body, user)


@router.post("/api/agent/chat/stream")
async def agent_chat_stream_api(
    body: ChatRequest,
    user: User = Depends(get_current_user),
):
    """规划书口径别名，与 /api/ai/chat/stream 相同。"""
    return _stream_response(body, user)


@router.get("/api/ai/chat/history")
async def chat_history_api(
    ticket_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
):
    """刷新续聊：只回 full（及摘要），不回 progress。"""
    rows = await asyncio.to_thread(
        list_chat_messages,
        user_id=user.id,
        ticket_id=ticket_id,
        include_progress=False,
    )
    # 前端气泡只要 user/assistant 的 full
    data = [
        {"role": r["role"], "content": r["content"]}
        for r in rows
        if r.get("kind") == "full" and r.get("role") in ("user", "assistant")
    ]
    return success_response(message="ok", data=data)
