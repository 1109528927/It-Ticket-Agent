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

/** 多格式入库：FormData 含 category、file，可选 title、enable_ocr */
export function ingestKbFile(formData) {
  return request({
    url: '/api/kb/ingest',
    method: 'post',
    data: formData,
    timeout: 60000
  })
}

export function getKbIngestJob(jobId) {
  return request({
    url: `/api/kb/ingest/jobs/${jobId}`,
    method: 'get'
  })
}

export function listKbIngestJobs(params) {
  return request({
    url: '/api/kb/ingest/jobs',
    method: 'get',
    params
  })
}
