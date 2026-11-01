import request from '@/utils/request'

export function getAutomationConfig() {
  return request({
    url: '/api/automation/config',
    method: 'get'
  })
}

export function saveAutomationConfig(data) {
  return request({
    url: '/api/automation/config',
    method: 'put',
    data
  })
}

export function listAutomationRuns(limit = 30) {
  return request({
    url: '/api/automation/runs',
    method: 'get',
    params: { limit }
  })
}

export function getAutomationRun(runId) {
  return request({
    url: `/api/automation/runs/${runId}`,
    method: 'get'
  })
}

export function runBacklogJob() {
  return request({
    url: '/api/automation/jobs/backlog',
    method: 'post',
    timeout: 300000
  })
}

export function runSlaJob() {
  return request({
    url: '/api/automation/jobs/sla',
    method: 'post',
    timeout: 120000
  })
}

export function retriageTicket(ticketId) {
  return request({
    url: `/api/automation/tickets/${ticketId}/triage`,
    method: 'post',
    timeout: 120000
  })
}

export function getTicketAssistantDraft(ticketId) {
  return request({
    url: `/api/automation/tickets/${ticketId}/draft`,
    method: 'get'
  })
}
