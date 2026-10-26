import request from '@/utils/request'

export function createSupportUser(data) {
  return request({
    url: '/api/user/support',
    method: 'post',
    data
  })
}
