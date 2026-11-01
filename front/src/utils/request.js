import axios from 'axios'

const instance = axios.create({
  baseURL: '',
  timeout: 10000
})

export function getErrorMessage(error, fallback = '请求失败') {
  const status = error?.response?.status
  // 代理连不上后端时常见 502，别和「没登录」搞混
  if (status === 502 || status === 503 || status === 504) {
    return '后端服务连不上（请确认 uvicorn 已启动），不是登录过期'
  }
  if (!error?.response && error?.message) {
    const msg = String(error.message)
    if (/network|timeout|exceeded/i.test(msg)) {
      return '网络异常或后端无响应，请确认服务已启动'
    }
  }

  const data = error?.response?.data
  if (!data) return error?.message || fallback

  if (typeof data.message === 'string' && data.message) {
    return data.message
  }
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : ''
        const msg = item.msg || ''
        return field ? `${field}: ${msg}` : msg
      })
      .filter(Boolean)
      .join('；')
  }
  if (typeof data.detail === 'string') return data.detail
  return fallback
}

instance.interceptors.request.use(
  function (config) {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  function (error) {
    return Promise.reject(error)
  }
)

instance.interceptors.response.use(
  function (response) {
    return response
  },
  function (error) {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      if (!location.pathname.includes('/login')) {
        location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default instance
