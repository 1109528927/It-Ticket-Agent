<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addTicketReply,
  changeTicketStatus,
  confirmTicketAction,
  getTicketDetail,
  proposeTicketAction,
  rejectTicketAction,
  toggleChecklistItem
} from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const resolving = ref(false)
const proposing = ref(false)
const actionBusyId = ref(null)
const detail = ref(null)
const content = ref('')

const proposeForm = reactive({
  action_type: 'reset_password',
  reason: '',
  group_name: ''
})

// 常用业务权限组；选「自定义」再手输
const PERMISSION_CUSTOM = '__custom__'
const permissionGroupOptions = [
  { value: 'vpn_users', label: 'vpn_users（VPN 开通）' },
  { value: 'shared_drive', label: 'shared_drive（共享盘）' },
  { value: 'dev_tools', label: 'dev_tools（开发工具）' },
  { value: 'email_ext', label: 'email_ext（外邮权限）' },
  { value: 'finance_ro', label: 'finance_ro（财务只读）' },
  { value: PERMISSION_CUSTOM, label: '自定义（手动输入）' }
]
const groupSelect = ref('')
const groupCustom = ref('')

const syncGroupName = () => {
  if (groupSelect.value === PERMISSION_CUSTOM) {
    proposeForm.group_name = groupCustom.value.trim()
  } else {
    proposeForm.group_name = groupSelect.value || ''
  }
}

const confirmVisible = ref(false)
const confirmRow = ref(null)
const confirmForm = reactive({
  new_password: '',
  new_password2: ''
})

const categoryLabel = {
  account: '账号',
  device: '设备',
  network: '网络',
  permission: '权限'
}
const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  pending_confirm: '待确认',
  resolved: '已解决',
  closed: '已关闭'
}
const priorityLabel = {
  low: '低',
  medium: '中',
  high: '高'
}
const eventLabel = {
  create: '创建',
  comment: '补充说明',
  claim: '认领',
  status: '改状态',
  reply: '回复',
  propose: '提出确认',
  confirm: '确认',
  reject: '拒绝',
  close: '关闭',
  handoff: '交接摘要',
  checklist: '处理清单',
  employee_confirm: '员工确认解决',
  employee_reopen: '员工反馈未解决'
}
const actionTypeLabel = {
  reset_password: '重置密码',
  change_permission: '变更权限'
}
const actionStatusLabel = {
  pending: '待确认',
  confirmed: '已确认',
  rejected: '已拒绝'
}

const canPropose = computed(() => detail.value?.status === 'processing')
const actions = computed(() => detail.value?.actions || [])
const checklist = computed(() => detail.value?.checklist || [])
const needsChecklist = computed(() =>
  ['device', 'network'].includes(detail.value?.category)
)
const checklistDone = computed(
  () => checklist.value.length > 0 && checklist.value.every((i) => i.checked)
)
const handoffText = computed(() => {
  const events = detail.value?.events || []
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].event_type === 'handoff' && events[i].detail) {
      return events[i].detail
    }
  }
  return ''
})

const payloadSummary = (row) => {
  const p = row.payload || {}
  if (row.action_type === 'reset_password') return `工号 ${p.target_employee_no || '—'}`
  if (row.action_type === 'change_permission') return `权限组 ${p.group_name || '—'}`
  return JSON.stringify(p)
}

const execSummary = (row) => {
  const er = row.execution_result
  if (!er) return row.execution_status || '—'
  if (typeof er === 'string') return er
  return er.message || row.execution_status || '—'
}

const load = async () => {
  loading.value = true
  try {
    const res = await getTicketDetail(route.params.id)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '加载失败')
      return
    }
    detail.value = body.data
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载失败'))
    if (e?.response?.status === 404) {
      router.push('/support/queue')
    }
  } finally {
    loading.value = false
  }
}

const submitReply = async () => {
  const text = content.value.trim()
  if (!text) {
    ElMessage.warning('请输入回复内容')
    return
  }
  submitting.value = true
  try {
    const res = await addTicketReply(route.params.id, { content: text })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '回复失败')
      return
    }
    detail.value = body.data
    content.value = ''
    ElMessage.success(body.message || '回复成功')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '回复失败'))
  } finally {
    submitting.value = false
  }
}

const onToggleChecklist = async (item, checked) => {
  try {
    const res = await toggleChecklistItem(route.params.id, item.id, checked)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '更新清单失败')
      await load()
      return
    }
    if (detail.value) {
      detail.value.checklist = body.data
    }
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '更新清单失败'))
    await load()
  }
}

const markResolved = async () => {
  if (needsChecklist.value && !checklistDone.value) {
    ElMessage.warning('请先勾选完处理清单再标记解决')
    return
  }
  resolving.value = true
  try {
    const res = await changeTicketStatus(route.params.id, { status: 'resolved' })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '改状态失败')
      return
    }
    ElMessage.success(body.message || '状态已更新')
    await load()
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '改状态失败'))
  } finally {
    resolving.value = false
  }
}

const buildPayload = () => {
  if (proposeForm.action_type === 'reset_password') {
    // 用工单详情里的提单人工号；后端还会再强制覆盖一次
    const no = (detail.value?.creator_employee_no || '').trim()
    return no ? { target_employee_no: no } : {}
  }
  return { group_name: proposeForm.group_name.trim() }
}

const submitPropose = async () => {
  if (!proposeForm.reason.trim()) {
    ElMessage.warning('请填写提出理由')
    return
  }
  if (proposeForm.action_type === 'reset_password') {
    if (!(detail.value?.creator_employee_no || '').trim()) {
      ElMessage.warning('工单缺少提单人工号，无法提出重置密码')
      return
    }
  }
  if (proposeForm.action_type === 'change_permission') {
    syncGroupName()
    if (!proposeForm.group_name) {
      ElMessage.warning('请选择或输入权限组')
      return
    }
  }
  proposing.value = true
  try {
    const res = await proposeTicketAction(route.params.id, {
      action_type: proposeForm.action_type,
      reason: proposeForm.reason.trim(),
      payload: buildPayload()
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '提出失败')
      return
    }
    detail.value = body.data
    proposeForm.reason = ''
    proposeForm.group_name = ''
    groupSelect.value = ''
    groupCustom.value = ''
    ElMessage.success(body.message || '已提出，请在下方待确认列表完成执行表单')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '提出失败'))
  } finally {
    proposing.value = false
  }
}

const openConfirm = (row) => {
  confirmRow.value = row
  confirmForm.new_password = ''
  confirmForm.new_password2 = ''
  confirmVisible.value = true
}

const insertHandoffToReply = () => {
  if (!handoffText.value) return
  const prefix = `【交接摘要】\n${handoffText.value}\n\n`
  content.value = content.value ? `${prefix}${content.value}` : prefix
  ElMessage.success('已插入回复开头')
}

const adoptDraftFromAssistant = () => {
  const draft = sessionStorage.getItem('assistant_draft') || ''
  if (!draft.trim()) {
    ElMessage.warning('暂无助手草稿，请先在助手页生成回复后点「存为草稿」')
    return
  }
  content.value = draft.trim()
  ElMessage.success('已采用助手草稿，请核对后发送')
}

const submitConfirm = async () => {
  const row = confirmRow.value
  if (!row) return

  const payload = {}
  if (row.action_type === 'reset_password') {
    const p1 = confirmForm.new_password.trim()
    const p2 = confirmForm.new_password2.trim()
    if (p1.length < 6) {
      ElMessage.warning('临时密码至少 6 位')
      return
    }
    if (p1 !== p2) {
      ElMessage.warning('两次输入的临时密码不一致')
      return
    }
    payload.new_password = p1
  }

  actionBusyId.value = row.id
  try {
    const res = await confirmTicketAction(route.params.id, row.id, payload)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '确认失败')
      return
    }
    detail.value = body.data
    confirmVisible.value = false
    ElMessage.success(body.message || '已确认并执行')
    if (row.action_type === 'reset_password') {
      const tip =
        '临时密码已设置，请尽快登录并用临时密码登录后修改。旧会话已失效。'
      content.value = content.value ? `${content.value}\n\n${tip}` : tip
    }
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '确认失败'))
  } finally {
    actionBusyId.value = null
  }
}

const onReject = async (row) => {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请填写拒绝理由', '拒绝高风险动作', {
      confirmButtonText: '拒绝',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '拒绝理由不能为空'
    })
    reason = (value || '').trim()
  } catch {
    return
  }
  actionBusyId.value = row.id
  try {
    const res = await rejectTicketAction(route.params.id, row.id, { reason })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '拒绝失败')
      return
    }
    detail.value = body.data
    ElMessage.success(body.message || '已拒绝')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '拒绝失败'))
  } finally {
    actionBusyId.value = null
  }
}

onMounted(async () => {
  await load()
  if (route.hash === '#risk-actions') {
    await nextTick()
    document.getElementById('risk-actions')?.scrollIntoView({ behavior: 'smooth' })
  }
})
</script>

<template>
  <div class="layout">
    <SupportAside active="queue" />
    <main class="main" v-loading="loading">
      <div class="head">
        <h2>处理工单</h2>
        <div class="head-actions">
          <el-button
            v-if="detail?.status === 'processing'"
            type="success"
            :loading="resolving"
            @click="markResolved"
          >
            标记解决
          </el-button>
          <el-button @click="router.push('/support/queue')">返回工单池</el-button>
        </div>
      </div>
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="编号">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            {{ statusLabel[detail.status] || detail.status }}
          </el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="类别">
            {{ categoryLabel[detail.category] || detail.category }}
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            {{ priorityLabel[detail.priority] || detail.priority }}
          </el-descriptions-item>
          <el-descriptions-item label="提单人">
            {{ detail.creator_username || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="提单人工号">
            {{ detail.creator_employee_no || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            <div class="desc">{{ detail.description }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="handoffText" class="handoff-card">
          <div class="handoff-title">员工交接摘要</div>
          <div class="handoff-body">{{ handoffText }}</div>
          <el-button type="primary" link @click="insertHandoffToReply">插入回复开头</el-button>
        </div>

        <template v-if="needsChecklist">
          <h3 class="block-title">
            处理清单
            <span class="chk-hint">（设备/网络类须全部勾选才能标记解决）</span>
          </h3>
          <div class="checklist-box">
            <el-checkbox
              v-for="item in checklist"
              :key="item.id"
              :model-value="item.checked"
              :disabled="detail.status !== 'processing'"
              class="chk-item"
              @change="(v) => onToggleChecklist(item, v)"
            >
              {{ item.label }}
            </el-checkbox>
            <p v-if="!checklist.length" class="hint">加载清单中或尚未生成…</p>
            <p v-else class="chk-status">
              {{ checklistDone ? '清单已完成' : `已勾选 ${checklist.filter((i) => i.checked).length}/${checklist.length}` }}
            </p>
          </div>
        </template>

        <h3 class="block-title">高风险动作（提出 → 待确认填表 → 已执行）</h3>
        <div v-if="canPropose" class="propose-box">
          <el-form label-width="96px" @submit.prevent>
            <el-form-item label="动作类型">
              <el-select v-model="proposeForm.action_type" style="width: 220px">
                <el-option
                  v-for="(label, value) in actionTypeLabel"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-if="proposeForm.action_type === 'reset_password'" label="目标工号">
              <span class="readonly-no">
                {{ detail.creator_employee_no || '—' }}
                <span class="readonly-tip">（自动取本单提单人，无需手填）</span>
              </span>
            </el-form-item>
            <el-form-item v-if="proposeForm.action_type === 'change_permission'" label="权限组">
              <div class="group-pick">
                <el-select
                  v-model="groupSelect"
                  clearable
                  placeholder="请选择权限组"
                  style="width: 320px"
                  @change="syncGroupName"
                >
                  <el-option
                    v-for="opt in permissionGroupOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <el-input
                  v-if="groupSelect === PERMISSION_CUSTOM"
                  v-model="groupCustom"
                  maxlength="64"
                  placeholder="输入组名，如 vpn_users"
                  style="width: 320px; margin-top: 8px"
                  @input="syncGroupName"
                />
              </div>
            </el-form-item>
            <el-form-item label="提出理由">
              <el-input
                v-model="proposeForm.reason"
                type="textarea"
                :rows="3"
                maxlength="500"
                show-word-limit
                style="max-width: 520px"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="proposing" @click="submitPropose">
                提出确认
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <p v-else class="hint">工单不在处理中时不能提出新动作（待确认请先确认或拒绝）。</p>

        <el-table :data="actions" empty-text="暂无高风险动作" id="risk-actions">
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              {{ actionTypeLabel[row.action_type] || row.action_type }}
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="理由" min-width="140" />
          <el-table-column label="参数摘要" min-width="120">
            <template #default="{ row }">{{ payloadSummary(row) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              {{ actionStatusLabel[row.status] || row.status }}
            </template>
          </el-table-column>
          <el-table-column label="执行结果" min-width="180">
            <template #default="{ row }">{{ execSummary(row) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button
                  type="primary"
                  link
                  :loading="actionBusyId === row.id"
                  @click="openConfirm(row)"
                >
                  确认执行
                </el-button>
                <el-button
                  type="danger"
                  link
                  :loading="actionBusyId === row.id"
                  @click="onReject(row)"
                >
                  拒绝
                </el-button>
              </template>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <h3 class="block-title">回复员工</h3>
        <div class="reply-box">
          <div class="reply-tools">
            <el-button size="small" @click="adoptDraftFromAssistant">采用助手草稿</el-button>
          </div>
          <el-input
            v-model="content"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="写给员工的处理说明"
          />
          <el-button
            type="primary"
            class="reply-btn"
            :loading="submitting"
            @click="submitReply"
          >
            发送回复
          </el-button>
        </div>

        <h3 class="block-title">操作记录</h3>
        <el-timeline v-if="detail.events?.length">
          <el-timeline-item
            v-for="ev in detail.events"
            :key="ev.id"
            :timestamp="ev.create_at"
            placement="top"
          >
            <div class="ev-type">{{ eventLabel[ev.event_type] || ev.event_type }}</div>
            <div class="ev-detail">{{ ev.detail || '—' }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录" />
      </template>

      <el-dialog
        v-model="confirmVisible"
        :title="confirmRow ? `确认执行：${actionTypeLabel[confirmRow.action_type] || confirmRow.action_type}` : '确认执行'"
        width="480px"
        destroy-on-close
      >
        <template v-if="confirmRow">
          <p class="dlg-line">参数：{{ payloadSummary(confirmRow) }}</p>
          <p class="dlg-line">理由：{{ confirmRow.reason }}</p>
          <el-form v-if="confirmRow.action_type === 'reset_password'" label-width="110px">
            <el-form-item label="临时新密码" required>
              <el-input
                v-model="confirmForm.new_password"
                type="password"
                show-password
                maxlength="64"
                placeholder="6～64 位，将写入本系统登录密码"
              />
            </el-form-item>
            <el-form-item label="再输一次" required>
              <el-input
                v-model="confirmForm.new_password2"
                type="password"
                show-password
                maxlength="64"
              />
            </el-form-item>
            <p class="dlg-hint">确认后旧登录会话立即失效；明文密码不会写入动作 payload。</p>
          </el-form>
          <p v-else class="dlg-hint">
            确认后将把本单提单人的业务权限组设为
            「{{ confirmRow.payload?.group_name || '—' }}」。
          </p>
        </template>
        <template #footer>
          <el-button @click="confirmVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="actionBusyId === confirmRow?.id"
            @click="submitConfirm"
          >
            确认并执行
          </el-button>
        </template>
      </el-dialog>
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
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.head-actions {
  display: flex;
  gap: 8px;
}
.desc {
  white-space: pre-wrap;
}
.block-title {
  margin: 28px 0 16px;
}
.propose-box {
  margin-bottom: 16px;
  max-width: 640px;
}
.hint {
  color: #888;
  margin-bottom: 12px;
}
.readonly-no {
  color: #303133;
}
.readonly-tip {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
.chk-hint {
  font-size: 13px;
  font-weight: 400;
  color: #909399;
}
.checklist-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
  max-width: 520px;
}
.chk-item {
  margin-right: 0;
}
.chk-status {
  margin: 4px 0 0;
  font-size: 13px;
  color: #606266;
}
.handoff-card {
  margin: 16px 0;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.handoff-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.handoff-body {
  white-space: pre-wrap;
  color: #606266;
  margin-bottom: 8px;
}
.reply-box {
  max-width: 640px;
}
.reply-tools {
  margin-bottom: 8px;
}
.reply-btn {
  margin-top: 12px;
}
.dlg-line {
  margin: 0 0 8px;
  color: #303133;
}
.dlg-hint {
  margin: 0;
  font-size: 12px;
  color: #909399;
}
.ev-type {
  font-weight: 600;
}
.ev-detail {
  color: #666;
  margin-top: 4px;
  white-space: pre-wrap;
}
.muted {
  color: #bbb;
}
</style>
