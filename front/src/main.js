import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { ElMessage } from 'element-plus'
import App from './App.vue'
import router from './router'
import {
  consumeAuthClearedHint,
  sanitizeAuthStorage,
  showPageHint
} from './utils/boot'

sanitizeAuthStorage()

window.addEventListener('error', (event) => {
  showPageHint(
    '页面加载失败',
    `原因：${event.message || '脚本运行出错'}。\n\n可先点下方按钮清除本地登录信息并刷新。若仍空白，打开 F12 看 Console 红色报错。`
  )
})

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  const msg =
    typeof reason === 'string'
      ? reason
      : reason?.message || '未处理的异步错误'
  showPageHint(
    '页面加载失败',
    `原因：${msg}。\n\n可先点下方按钮清除本地登录信息并刷新。若仍空白，打开 F12 看 Console 红色报错。`
  )
})

try {
  const app = createApp(App)
  app.config.errorHandler = (err) => {
    console.error(err)
    showPageHint(
      '页面运行出错',
      `原因：${err?.message || String(err)}。\n\n可先点下方按钮清除本地登录信息并刷新。`
    )
  }
  app.use(router)
  app.use(ElementPlus, { locale: zhCn })
  app.mount('#app')

  if (consumeAuthClearedHint()) {
    ElMessage.warning('本地登录信息已损坏并已清除，请重新登录')
  }
} catch (err) {
  console.error(err)
  showPageHint(
    '应用启动失败',
    `原因：${err?.message || String(err)}。\n\n可先点下方按钮清除本地登录信息并刷新。`
  )
}
