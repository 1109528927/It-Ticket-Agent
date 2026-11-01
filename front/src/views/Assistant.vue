<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatHistoryApi, chatStreamApi } from '@/api/ai'
import { createTicket, listMyTickets, listSupportTickets } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import {
  clearTicketCreateDraft,
  readTicketCreateDraft,
  saveReplyDraft,
  saveTicketCreateDraft
} from '@/utils/assistantDraft'
import SupportAside from '@/components/SupportAside.vue'
import EmployeeAside from '@/components/EmployeeAside.vue'

const router = useRouter()

const user = JSON.parse(localStorage.getItem('userInfo') || '{}')
const isSupport = computed(() => user.role === 'support')
const sending = ref(false)
const creating = ref(false)
const statusText = ref('')
const input = ref('')
const listRef = ref(null)
const messages = reactive([])
const ticketId = ref(null)
const ticketOptions = ref([])
const threadId = ref(null)
/** 员工：对话预填待确认建单 */
const pendingDraft = ref(null)

const categoryLabel = {
  account: '账号',
  device: '设备',
  network: '网络',
  permission: '权限'
}

const priorityLabel = {
  low: '低',
  medium: '中',
  high: '高'
}

const threadStorageKey = (tid) =>
  `assistant_thread_${user.id || 0}_${user.role || 'x'}_t${tid ?? 0}`

const readStoredThread = () => {
  try {
    return sessionStorage.getItem(threadStorageKey(ticketId.value)) || null
  } catch {
    return null
  }
}

const writeStoredThread = (id) => {
  if (!id) return
  threadId.value = id
  try {
    sessionStorage.setItem(threadStorageKey(ticketId.value), id)
  } catch {
    /* ignore */
  }
}

const syncPendingDraftFromStorage = () => {
  if (isSupport.value) {
    pendingDraft.value = null
    return
  }
  pendingDraft.value = readTicketCreateDraft()
}

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
  threadId.value = readStoredThread()
  loadHistory()
})

onMounted(async () => {
  threadId.value = readStoredThread()
  syncPendingDraftFromStorage()
  await loadTickets()
  await loadHistory()
})

const saveLastAssistantAsDraft = () => {
  if (!isSupport.value) {
    ElMessage.warning('员工请用对话生成工单预填，就绪后在下方点「确认建单」')
    return
  }
  if (!ticketId.value) {
    ElMessage.warning('请先关联工单，再存回复草稿')
    return
  }
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === 'assistant' && messages[i].content?.trim()) {
      saveReplyDraft(ticketId.value, messages[i].content.trim())
      ElMessage.success('已存为处理页草稿，打开该单即可预填，核对后一键发送或改后发送')
      return
    }
  }
  ElMessage.warning('没有可保存的助手回复')
}

const dismissPendingDraft = () => {
  clearTicketCreateDraft()
  pendingDraft.value = null
}

const confirmCreateTicket = async () => {
  const draft = pendingDraft.value || readTicketCreateDraft()
  if (!draft?.title || !draft?.description || !draft?.category) {
    ElMessage.warning('暂无待确认的工单预填，请先对话生成')
    return
  }
  if (creating.value) return

  creating.value = true
  try {
    const res = await createTicket({
      category: draft.category,
      title: String(draft.title).trim(),
      description: String(draft.description).trim(),
      priority: draft.priority || 'medium'
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '创建失败')
      return
    }
    clearTicketCreateDraft()
    pendingDraft.value = null
    const created = body.data || {}
    const newId = created?.id
    if (created.high_risk) {
      ElMessage({
        type: 'warning',
        duration: 8000,
        showClose: true,
        message: body.message || '工单已创建（高风险，需客服人工处理）'
      })
    } else {
      ElMessage.success(body.message || '工单已创建')
    }
    await loadTickets()
    if (newId != null) {
      ticketId.value = newId
      router.push(`/employee/tickets/${newId}`)
    } else {
      router.push('/employee/tickets')
    }
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '创建失败'))
  } finally {
    creating.value = false
  }
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
        if (event.type === 'thread' && event.thread_id) {
          writeStoredThread(event.thread_id)
          return
        }
        if (event.type === 'ticket_draft' && event.draft) {
          saveTicketCreateDraft(event.draft)
          pendingDraft.value = { ...event.draft }
          ElMessage.success({
            message: '工单预填已就绪，请在下方核对后点「确认建单」',
            duration: 5000
          })
          nextTick(() => scrollBottom())
          return
        }
        if (event.type === 'reply_draft' && event.content) {
          const tid = event.ticket_id ?? ticketId.value
          if (tid != null) {
            saveReplyDraft(tid, event.content)
            ElMessage.success('回复草稿已就绪，打开处理页会预填，核对后发送即可')
          }
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
          if (event.thread_id) writeStoredThread(event.thread_id)
          statusText.value = ''
        }
      },
      ticketId.value,
      threadId.value
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
        <template v-if="isSupport">
          关联工单后可让助手生成「带依据的回复草稿」，处理页一键采用；高危仍须页面确认。
        </template>
        <template v-else>
          直接说现象，助手追问补全后给出预填；在本页点「确认建单」即可创建（仍由你确认，不会自动落库）。
        </template>
      </p>
      <div class="toolbar">
        <span class="label">关联工单</span>
        <el-select
          v-model="ticketId"
          clearable
          filterable
          :placeholder="isSupport ? '回复草稿须关联工单' : '查单/交接可选；提单预填可不选'"
          style="width: 360px"
        >
          <el-option
            v-for="opt in ticketOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button v-if="isSupport" size="small" @click="saveLastAssistantAsDraft">
          存为处理页草稿
        </el-button>
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
        <div v-if="!isSupport && pendingDraft" class="draft-card">
          <div class="draft-title">待确认工单预填</div>
          <div class="draft-row">
            <span class="k">类别</span>
            {{ categoryLabel[pendingDraft.category] || pendingDraft.category }}
          </div>
          <div class="draft-row">
            <span class="k">优先级</span>
            {{ priorityLabel[pendingDraft.priority] || pendingDraft.priority || '中' }}
          </div>
          <div class="draft-row">
            <span class="k">标题</span>
            {{ pendingDraft.title }}
          </div>
          <div class="draft-row block">
            <span class="k">描述</span>
            <div class="draft-desc">{{ pendingDraft.description }}</div>
          </div>
          <div v-if="pendingDraft.missing_info" class="draft-miss">
            仍缺：{{ pendingDraft.missing_info }}
          </div>
          <div class="draft-actions">
            <el-button
              type="primary"
              :loading="creating"
              :disabled="sending"
              @click="confirmCreateTicket"
            >
              确认建单
            </el-button>
            <el-button :disabled="creating" @click="dismissPendingDraft">放弃预填</el-button>
            <el-button
              link
              type="primary"
              :disabled="creating"
              @click="router.push('/employee/tickets/create')"
            >
              去新建页再改
            </el-button>
          </div>
        </div>
        <el-empty
          v-if="!messages.length && !(pendingDraft && !isSupport)"
          description="说一句试试，例如：电脑登不上 / 池子里有哪些单"
        />
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
.draft-card {
  margin: 16px 0 8px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #c6e2ff;
  border-radius: 8px;
  max-width: 100%;
}
.draft-title {
  font-weight: 600;
  margin-bottom: 10px;
  color: #303133;
}
.draft-row {
  font-size: 13px;
  margin-bottom: 6px;
  line-height: 1.5;
}
.draft-row .k {
  display: inline-block;
  min-width: 48px;
  color: #909399;
  margin-right: 8px;
}
.draft-row.block .k {
  display: block;
  margin-bottom: 4px;
}
.draft-desc {
  white-space: pre-wrap;
  color: #303133;
  background: #f5f7fa;
  padding: 8px 10px;
  border-radius: 4px;
}
.draft-miss {
  font-size: 12px;
  color: #e6a23c;
  margin: 8px 0;
}
.draft-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
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
