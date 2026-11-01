import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', name: 'Login', component: () => import('@/views/Login.vue') },
    {
      path: '/employee/home',
      redirect: '/employee/tickets'
    },
    {
      path: '/employee/tickets',
      name: 'EmployeeTickets',
      meta: { role: 'employee' },
      component: () => import('@/views/employee/TicketList.vue')
    },
    {
      path: '/employee/tickets/create',
      name: 'EmployeeTicketCreate',
      meta: { role: 'employee' },
      component: () => import('@/views/employee/TicketCreate.vue')
    },
    {
      path: '/employee/tickets/:id',
      name: 'EmployeeTicketDetail',
      meta: { role: 'employee' },
      component: () => import('@/views/employee/TicketDetail.vue')
    },

    {
      path: '/support/home',
      redirect: '/support/queue'
    },
    {
      path: '/support/queue',
      name: 'SupportQueue',
      meta: { role: 'support' },
      component: () => import('@/views/support/Queue.vue')
    },
    {
      path: '/support/tickets/:id',
      name: 'SupportHandle',
      meta: { role: 'support' },
      component: () => import('@/views/support/Handle.vue')
    },
    {
      path: '/support/users/create',
      name: 'SupportCreateUser',
      meta: { role: 'support' },
      component: () => import('@/views/support/CreateUser.vue')
    },
    {
      path: '/support/kb',
      name: 'SupportKbList',
      meta: { role: 'support' },
      component: () => import('@/views/support/KbList.vue')
    },
    {
      path: '/support/automation',
      name: 'SupportAutomation',
      meta: { role: 'support' },
      component: () => import('@/views/support/Automation.vue')
    },

    {
      path: '/support/kb/edit/:id?',
      name: 'SupportKbEdit',
      meta: { role: 'support' },
      component: () => import('@/views/support/KbEdit.vue')
    },
    {
      path: '/assistant',
      name: 'Assistant',
      component: () => import('@/views/Assistant.vue')
    }
  ]
})

function readRole() {
  try {
    const raw = localStorage.getItem('userInfo')
    if (!raw) return ''
    return JSON.parse(raw).role || ''
  } catch {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    sessionStorage.setItem('auth_storage_cleared', '1')
    return ''
  }
}

function readToken() {
  const raw = localStorage.getItem('token')
  if (raw == null) return ''
  const token = String(raw).trim()
  // 脏数据：有 key 但空串 / "null"，当未登录，避免直输子路径还能进业务页
  if (!token || token === 'null' || token === 'undefined') {
    if (raw != null && raw !== '') {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
    }
    return ''
  }
  return token
}

router.beforeEach((to) => {
  const token = readToken()
  const role = readRole()

  // token 在但角色丢了：清掉，否则会在 /login 和 /employee/home 之间死循环（白屏转圈）
  if (token && !role) {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    if (to.path !== '/login') return '/login'
    return true
  }

  if (to.path === '/login') {
    if (!token) return true
    return role === 'support' ? '/support/home' : '/employee/home'
  }

  // 无 token：任意业务子路径（含直接地址栏输入）一律回登录
  if (!token) return '/login'
  if (to.meta.role && to.meta.role !== role) {
    return role === 'support' ? '/support/home' : '/employee/home'
  }
  return true
})

export default router
