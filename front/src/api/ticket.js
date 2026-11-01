import request from '@/utils/request'

export function listMyTickets(params) {
  return request({
    url: '/api/tickets',
    method: 'get',
    params
  })
}

export function listSupportTickets(params) {
  return request({
    url: '/api/tickets',
    method: 'get',
    params
  })
}

export function createTicket(data) {
  return request({
    url: '/api/tickets',
    method: 'post',
    data
  })
}

export function getTicketDetail(id) {
  return request({
    url: `/api/tickets/${id}`,
    method: 'get'
  })
}

export function addTicketComment(id, data) {
  return request({
    url: `/api/tickets/${id}/comments`,
    method: 'post',
    data
  })
}

export function closeTicket(id) {
  return request({
    url: `/api/tickets/${id}/close`,
    method: 'post'
  })
}

export function claimTicket(id) {
  return request({
    url: `/api/tickets/${id}/claim`,
    method: 'post'
  })
}

export function changeTicketStatus(id, data) {
  return request({
    url: `/api/tickets/${id}/status`,
    method: 'post',
    data
  })
}

export function addTicketReply(id, data) {
  return request({
    url: `/api/tickets/${id}/replies`,
    method: 'post',
    data
  })
}

export function proposeTicketAction(id, data) {
  return request({
    url: `/api/tickets/${id}/actions`,
    method: 'post',
    data
  })
}

export function confirmTicketAction(ticketId, actionId, data) {
  return request({
    url: `/api/tickets/${ticketId}/actions/${actionId}/confirm`,
    method: 'post',
    data: data || {}
  })
}

export function rejectTicketAction(ticketId, actionId, data) {
  return request({
    url: `/api/tickets/${ticketId}/actions/${actionId}/reject`,
    method: 'post',
    data
  })
}

export function toggleChecklistItem(ticketId, itemId, checked) {
  return request({
    url: `/api/tickets/${ticketId}/checklist/${itemId}`,
    method: 'patch',
    data: { checked }
  })
}

export function employeeConfirmResolved(id) {
  return request({
    url: `/api/tickets/${id}/employee-confirm`,
    method: 'post'
  })
}

export function employeeReopenUnresolved(id, data) {
  return request({
    url: `/api/tickets/${id}/employee-reopen`,
    method: 'post',
    data
  })
}

export function adoptTicketDraft(id) {
  return request({
    url: `/api/tickets/${id}/adopt-draft`,
    method: 'post'
  })
}

export function oneClickExecuteTicket(id) {
  return request({
    url: `/api/tickets/${id}/one-click-execute`,
    method: 'post'
  })
}

export function getDashboardStats() {
  return request({
    url: '/api/dashboard/stats',
    method: 'get'
  })
}
