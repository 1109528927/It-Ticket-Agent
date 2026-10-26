/** 启动或本地登录信息出问题时，避免整页空白。 */

export function showPageHint(title, detail) {
  const el = document.querySelector('#app')
  if (!el) return
  el.innerHTML = `
    <div style="
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      padding:24px;font-family:system-ui,sans-serif;background:#f5f7fa;box-sizing:border-box;
    ">
      <div style="
        max-width:480px;width:100%;background:#fff;border-radius:10px;
        padding:24px 28px;box-shadow:0 8px 24px rgba(0,0,0,.08);
      ">
        <h2 style="margin:0 0 12px;font-size:18px;color:#303133;">${title}</h2>
        <p style="margin:0 0 16px;line-height:1.6;color:#606266;white-space:pre-wrap;">${detail}</p>
        <button type="button" id="boot-clear-reload" style="
          padding:8px 16px;border:0;border-radius:6px;background:#409eff;color:#fff;cursor:pointer;
        ">清除本地登录信息并刷新</button>
      </div>
    </div>
  `
  document.getElementById('boot-clear-reload')?.addEventListener('click', () => {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    sessionStorage.removeItem('auth_storage_cleared')
    location.href = '/login'
  })
}

/** 检查并清理损坏 / 残缺的登录态；返回是否清理过 */
export function sanitizeAuthStorage() {
  const token = localStorage.getItem('token')
  const raw = localStorage.getItem('userInfo')

  // 有 token 没 userInfo，或反过来，都会让路由在登录页和首页之间死转
  if ((token && !raw) || (!token && raw)) {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    sessionStorage.setItem('auth_storage_cleared', '1')
    return true
  }
  if (!raw) return false

  try {
    const info = JSON.parse(raw)
    if (!info || typeof info !== 'object') throw new Error('invalid')
    if (info.role !== 'employee' && info.role !== 'support') {
      throw new Error('bad_role')
    }
    return false
  } catch {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    sessionStorage.setItem('auth_storage_cleared', '1')
    return true
  }
}

export function consumeAuthClearedHint() {
  if (sessionStorage.getItem('auth_storage_cleared') !== '1') return false
  sessionStorage.removeItem('auth_storage_cleared')
  return true
}
