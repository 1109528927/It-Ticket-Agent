/** 助手草稿：工单预填 / 客服回复（sessionStorage） */

export const TICKET_CREATE_DRAFT_KEY = 'ticket_create_draft'

export function replyDraftKey(ticketId) {
  return `assistant_draft_${ticketId}`
}

export function saveTicketCreateDraft(draft) {
  if (!draft || typeof draft !== 'object') return
  sessionStorage.setItem(TICKET_CREATE_DRAFT_KEY, JSON.stringify(draft))
}

export function readTicketCreateDraft() {
  try {
    const raw = sessionStorage.getItem(TICKET_CREATE_DRAFT_KEY)
    if (!raw) return null
    const data = JSON.parse(raw)
    if (!data?.title || !data?.description || !data?.category) return null
    return data
  } catch {
    return null
  }
}

export function clearTicketCreateDraft() {
  sessionStorage.removeItem(TICKET_CREATE_DRAFT_KEY)
}

export function saveReplyDraft(ticketId, content) {
  const text = (content || '').trim()
  if (!ticketId || !text) return
  sessionStorage.setItem(replyDraftKey(ticketId), text)
  // 兼容旧键：无票号时处理页仍可读
  sessionStorage.setItem('assistant_draft', text)
}

export function readReplyDraft(ticketId) {
  if (ticketId != null) {
    const keyed = sessionStorage.getItem(replyDraftKey(ticketId))
    if (keyed && keyed.trim()) return keyed.trim()
  }
  const legacy = sessionStorage.getItem('assistant_draft') || ''
  return legacy.trim()
}
