<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatHistoryApi, chatStreamApi } from '@/api/ai'
import { listMyTickets, listSupportTickets } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'
import EmployeeAside from '@/components/EmployeeAside.vue'

const router = useRouter()

const user = JSON.parse(localStorage.getItem('userInfo') || '{}')
const isSupport = computed(() => user.role === 'support')
const sending = ref(false)
const statusText = ref('')
const input = ref('')
const listRef = ref(null)
const messages = reactive([])
const ticketId = ref(null)
const ticketOptions = ref([])

const scrollBottom = async () => {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

const loadTickets = async () => {
  try {
    const api = isSupport.value ? listSupportTickets : listMyTickets
    const res = await api({})
    const body = res.data
    const rows = body?.data?.items || body?.data || []
    ticketOptions.value = (Array.isArray(rows) ? rows : []).map((t) => ({
      value: t.id,
      label: `#${t.id} ${t.title}（${t.status}）`
    }))
  } catch {
    ticketOptions.value = []
  }
}

const loadHistory = async () => {
  messages.splice(0, messages.length)
  try {
    const res = await chatHistoryApi(ticketId.value)
    const rows = res.data?.data || []
    for (const row of rows) {
      if (row.role === 'user' || row.role === 'assistant') {
        messages.push({ role: row.role, content: row.content })
      }
    }
  } catch {
    /* 无历史就算了 */
  }
  await scrollBottom()
}

watch(ticketId, () => {
  loadHistory()
})

onMounted(async () => {
  await loadTickets()
  await loadHistory()
})

const saveLastAssistantAsDraft = () => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'assistant' && messages[i].content?.trim()) {
      sessionStorage.setItem('assistant_draft', messages[i].content.trim())
      ElMessage.success('已存为草稿，可在处理页点「采用助手草稿」')
      return
    }
  }
  ElMessage.warning('没有可保存的助手回复')
}

const goHandleConfirm = () => {
  if (!isSupport.value) {
    ElMessage.warning('仅客服可进入处理页确认')
    return
  }
  if (!ticketId.value) {
    ElMessage.warning('请先关联工单')
    return
  }
  router.push({
    path: `/support/tickets/${ticketId.value}`,
    hash: '#risk-actions'
  })
}

const send = async () => {
  const text = input.value.trim()
  if (!text || sending.value) return

  messages.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  statusText.value = '正在生成…'
  await scrollBottom()

  messages.push({ role: 'assistant', content: '' })
  const assistantIndex = messages.length - 1

  try {
    // status 只进 statusText，不进 messages（灰字不回灌）
    const history = messages
      .slice(0, -1)
      .map((m) => ({ role: m.role, content: m.content }))
      .filter((m) => m.content)

    await chatStreamApi(
      history,
      (event) => {
        if (event.type === 'status') {
          statusText.value = event.message || ''
          return
        }
        if (event.type === 'token' && event.content) {
          messages[assistantIndex].content += event.content
          scrollBottom()
          return
        }
        if (event.type === 'error') {
          throw new Error(event.message || '对话失败')
        }
        if (event.type === 'done') {
          statusText.value = ''
        }
      },
      ticketId.value
    )

    if (!messages[assistantIndex].content.trim()) {
      messages.splice(assistantIndex, 1)
      ElMessage.warning('大模型没有返回内容')
    }
  } catch (e) {
    messages.splice(assistantIndex, 1)
    messages.pop()
    ElMessage.error(getErrorMessage(e, e?.message || '对话失败'))
  } finally {
    sending.value = false
    statusText.value = ''
  }
}
</script>

<template>
  <div class="layout">
    <SupportAside v-if="isSupport" active="assistant" />
    <EmployeeAside v-else active="assistant" />
    <main class="main">
      <h2>工单助手</h2>
      <p class="hint">
        SSE 流式输出。灰字进度只显示在下方，不会写进对话气泡。可选关联工单以便续聊和加载 Skill。
        助手挂了不影响工单页认领与确认。
      </p>
      <div class="toolbar">
        <span class="label">关联工单</span>
        <el-select
          v-model="ticketId"
          clearable
          filterable
          placeholder="不选则闲聊（不加载 Skill）"
          style="width: 360px"
        >
          <el-option
            v-for="opt in ticketOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button size="small" @click="saveLastAssistantAsDraft">存为草稿</el-button>
        <el-button
          v-if="isSupport"
          size="small"
          type="warning"
          @click="goHandleConfirm"
        >
          去处理页确认
        </el-button>
      </div>
      <div ref="listRef" class="list">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="bubble"
          :class="m.role"
        >
          <div class="role">{{ m.role === 'user' ? '我' : '助手' }}</div>
          <div class="content">{{ m.content || (sending && i === messages.length - 1 ? '…' : '') }}</div>
        </div>
        <el-empty v-if="!messages.length" description="说一句试试，例如：池子里有哪些单" />
      </div>
      <p v-if="statusText" class="status">{{ statusText }}</p>
      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          placeholder="输入问题，Enter 发送（Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :loading="sending" @click="send">发送</el-button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}
.main {
  flex: 1;
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  max-width: 900px;
}
.hint {
  color: #888;
  margin: 0 0 12px;
  font-size: 13px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbar .label {
  font-size: 13px;
  color: #666;
}
.status {
  color: #909399;
  font-size: 13px;
  margin: 8px 0 0;
}
.list {
  flex: 1;
  overflow: auto;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 16px;
  min-height: 320px;
  background: #fafafa;
}
.bubble {
  margin-bottom: 12px;
  max-width: 85%;
}
.bubble.user {
  margin-left: auto;
  text-align: right;
}
.bubble .role {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}
.bubble .content {
  display: inline-block;
  text-align: left;
  white-space: pre-wrap;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #eee;
}
.bubble.user .content {
  background: #ecf5ff;
  border-color: #d9ecff;
}
.composer {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.composer .el-textarea {
  flex: 1;
}
</style>
