import request from '@/utils/request'

export function listKbArticles(params) {
  return request({
    url: '/api/kb',
    method: 'get',
    params
  })
}

export function getKbArticle(id) {
  return request({
    url: `/api/kb/${id}`,
    method: 'get'
  })
}

export function createKbArticle(data) {
  return request({
    url: '/api/kb',
    method: 'post',
    data
  })
}

export function updateKbArticle(id, data) {
  return request({
    url: `/api/kb/${id}`,
    method: 'put',
    data
  })
}

export function deleteKbArticle(id) {
  return request({
    url: `/api/kb/${id}`,
    method: 'delete'
  })
}
