import request from '@/utils/request'

/** 整包多轮对话 POST /api/ai/chat */
export function chatApi(messages, ticketId) {
  return request({
    url: '/api/ai/chat',
    method: 'post',
    data: { messages, ticket_id: ticketId ?? null },
    timeout: 90000
  })
}

/** 业务图整包 POST /api/ai/agent */
export function agentApi(messages, ticketId) {
  return request({
    url: '/api/ai/agent',
    method: 'post',
    data: { messages, ticket_id: ticketId ?? null },
    timeout: 90000
  })
}

/** 刷新续聊：只要 full，不要 progress */
export function chatHistoryApi(ticketId) {
  return request({
    url: '/api/ai/chat/history',
    method: 'get',
    params: ticketId != null ? { ticket_id: ticketId } : {}
  })
}

/**
 * 流式对话主路径 POST /api/ai/chat/stream（SSE）
 * status 灰字只给 onEvent，不要推进 messages 数组。
 */
export async function chatStreamApi(messages, onEvent, ticketId) {
  const token = localStorage.getItem('token')
  const res = await fetch('/api/ai/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      messages,
      ticket_id: ticketId ?? null
    })
  })
  if (res.status === 401) throw new Error('登录已失效，请重新登录')
  if (!res.ok || !res.body) throw new Error('流式接口请求失败')

  const contentType = res.headers.get('content-type') || ''
  if (!contentType.includes('text/event-stream')) {
    const payload = await res.json().catch(() => null)
    throw new Error(payload?.message || payload?.detail || '流式接口返回异常')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.trim().startsWith('data:'))
      if (!line) continue
      const raw = line.trim().slice(5).trim()
      if (!raw) continue
      onEvent(JSON.parse(raw))
    }
  }
}
