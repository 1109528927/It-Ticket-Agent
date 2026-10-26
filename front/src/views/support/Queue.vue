<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changeTicketStatus, claimTicket, listSupportTickets } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const router = useRouter()
const loading = ref(false)
const claimingId = ref(null)
const statusChangingId = ref(null)
const rows = ref([])
const filters = reactive({
  scope: '',
  status: ''
})

const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  pending_confirm: '待确认',
  resolved: '已解决',
  closed: '已关闭'
}
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

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.scope) params.scope = filters.scope
    if (filters.status) params.status = filters.status
    const res = await listSupportTickets(params)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '加载失败')
      return
    }
    rows.value = body.data?.items || []
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const onClaim = async (row) => {
  claimingId.value = row.id
  try {
    const res = await claimTicket(row.id)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '认领失败')
      return
    }
    ElMessage.success(body.message || '认领成功')
    await load()
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '认领失败'))
  } finally {
    claimingId.value = null
  }
}

const onMarkResolved = async (row) => {
  statusChangingId.value = row.id
  try {
    const res = await changeTicketStatus(row.id, { status: 'resolved' })
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
    statusChangingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="layout">
    <SupportAside active="queue" />
    <main class="main">
      <h2>工单池</h2>
      <div class="filters">
        <el-select v-model="filters.scope" clearable placeholder="认领" style="width: 160px" @change="load">
          <el-option label="未认领" value="unclaimed" />
          <el-option label="我认领的" value="mine" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 140px" @change="load">
          <el-option v-for="(label, value) in statusLabel" :key="value" :label="label" :value="value" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="id" label="编号" width="80" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="类别" width="100">
          <template #default="{ row }">{{ categoryLabel[row.category] || row.category }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">{{ statusLabel[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">{{ priorityLabel[row.priority] || row.priority }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="180" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              type="primary"
              link
              :loading="claimingId === row.id"
              @click.stop="onClaim(row)"
            >
              认领
            </el-button>
            <template v-else>
              <el-button
                type="primary"
                link
                @click.stop="router.push(`/support/tickets/${row.id}`)"
              >
                处理
              </el-button>
              <el-button
                v-if="row.status === 'processing'"
                type="success"
                link
                :loading="statusChangingId === row.id"
                @click.stop="onMarkResolved(row)"
              >
                标记解决
              </el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="工单池是空的" />
        </template>
      </el-table>
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
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
