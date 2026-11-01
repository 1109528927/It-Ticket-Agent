<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addTicketComment,
  closeTicket,
  employeeConfirmResolved,
  employeeReopenUnresolved,
  getTicketDetail
} from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import EmployeeAside from '@/components/EmployeeAside.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const closing = ref(false)
const confirming = ref(false)
const reopening = ref(false)
const detail = ref(null)
const comment = ref('')

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
  employee_reopen: '员工反馈未解决',
  risk_notice: '高风险说明',
  auto_reply: '系统自动回复',
  agent_draft: '助手草稿',
  auto_triage: '自动初审'
}
const actionTypeLabel = {
  reset_password: '重置密码',
  change_permission: '变更权限'
}
const actionStatusLabel = {
  pending: '待客服确认',
  confirmed: '已执行',
  rejected: '已拒绝'
}

const actions = computed(() => detail.value?.actions || [])

const actionResultText = (row) => {
  if (row.status === 'pending') return '等待客服在处理页确认'
  if (row.status === 'rejected') return '客服已拒绝'
  const er = row.execution_result
  if (er && typeof er === 'object' && er.message) {
    // 脱敏：不展示任何像密码的字段
    return er.message
  }
  if (row.action_type === 'reset_password') return '客服已确认重置密码（请用临时密码登录）'
  if (row.action_type === 'change_permission') return '客服已确认变更权限组'
  return row.execution_status || '已处理'
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
      router.push('/employee/tickets')
    }
  } finally {
    loading.value = false
  }
}

const canCancel = computed(() => detail.value?.status === 'pending')
const canConfirmResolved = computed(() => detail.value?.status === 'resolved')

const submitComment = async () => {
  const text = comment.value.trim()
  if (!text) {
    ElMessage.warning('请输入补充说明')
    return
  }
  submitting.value = true
  try {
    const res = await addTicketComment(route.params.id, { detail: text })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '补充失败')
      return
    }
    detail.value = body.data
    comment.value = ''
    ElMessage.success(body.message || '补充成功')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '补充失败'))
  } finally {
    submitting.value = false
  }
}

const onConfirmResolved = async () => {
  try {
    await ElMessageBox.confirm('确认问题已解决？确认后工单将关闭。', '确认解决', {
      type: 'success',
      confirmButtonText: '确认解决',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  confirming.value = true
  try {
    const res = await employeeConfirmResolved(route.params.id)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '确认失败')
      return
    }
    detail.value = body.data
    ElMessage.success(body.message || '已关闭')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '确认失败'))
  } finally {
    confirming.value = false
  }
}

const onReopenUnresolved = async () => {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请说明仍未解决的原因', '仍未解决', {
      confirmButtonText: '重新打开',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '原因不能为空'
    })
    reason = (value || '').trim()
  } catch {
    return
  }
  reopening.value = true
  try {
    const res = await employeeReopenUnresolved(route.params.id, { reason })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '操作失败')
      return
    }
    detail.value = body.data
    ElMessage.success(body.message || '已重新打开')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '操作失败'))
  } finally {
    reopening.value = false
  }
}

const cancelTicket = async () => {
  try {
    await ElMessageBox.confirm('确认撤销这张还未被认领的工单？', '撤销工单', {
      type: 'warning',
      confirmButtonText: '确认撤销',
      cancelButtonText: '再想想'
    })
  } catch {
    return
  }

  closing.value = true
  try {
    const res = await closeTicket(route.params.id)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '撤销失败')
      return
    }
    ElMessage.success(body.message || '撤销成功')
    router.push('/employee/tickets')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '撤销失败'))
  } finally {
    closing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="layout">
    <EmployeeAside active="list" />
    <main class="main" v-loading="loading">
      <div class="head">
        <h2>工单详情</h2>
        <div class="head-actions">
          <el-button
            v-if="canConfirmResolved"
            type="success"
            :loading="confirming"
            @click="onConfirmResolved"
          >
            确认已解决
          </el-button>
          <el-button
            v-if="canConfirmResolved"
            type="warning"
            plain
            :loading="reopening"
            @click="onReopenUnresolved"
          >
            仍未解决
          </el-button>
          <el-button
            v-if="canCancel"
            type="danger"
            plain
            :loading="closing"
            @click="cancelTicket"
          >
            撤销工单
          </el-button>
          <el-button @click="router.push('/employee/tickets')">返回列表</el-button>
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
          <el-descriptions-item label="描述" :span="2">
            <div class="desc">{{ detail.description }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detail.updated_at }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.create_at }}</el-descriptions-item>
        </el-descriptions>

        <template v-if="actions.length">
          <h3 class="timeline-title">高风险处理进度</h3>
          <el-table :data="actions" size="small">
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                {{ actionTypeLabel[row.action_type] || row.action_type }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                {{ actionStatusLabel[row.status] || row.status }}
              </template>
            </el-table-column>
            <el-table-column label="结果说明" min-width="220">
              <template #default="{ row }">{{ actionResultText(row) }}</template>
            </el-table-column>
          </el-table>
        </template>

        <h3 class="timeline-title">补充说明</h3>
        <div class="comment-box">
          <el-input
            v-model="comment"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="补充现象、进度等"
          />
          <el-button
            type="primary"
            class="comment-btn"
            :loading="submitting"
            @click="submitComment"
          >
            提交补充
          </el-button>
        </div>

        <h3 class="timeline-title">操作记录</h3>
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
.timeline-title {
  margin: 28px 0 16px;
}
.comment-box {
  max-width: 640px;
}
.comment-btn {
  margin-top: 12px;
}
.ev-type {
  font-weight: 600;
}
.ev-detail {
  color: #666;
  margin-top: 4px;
  white-space: pre-wrap;
}
</style>
