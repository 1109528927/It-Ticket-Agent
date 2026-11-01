<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listMyTickets } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import EmployeeAside from '@/components/EmployeeAside.vue'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const filters = reactive({
  status: '',
  category: ''
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
  waiting_feedback: '等你反馈',
  auto_resolved: '系统已自动结案',
  need_manual: '已升级人工',
  resolved: '已解决',
  closed: '已关闭'
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
    if (filters.status) params.status = filters.status
    if (filters.category) params.category = filters.category
    const res = await listMyTickets(params)
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

onMounted(load)
</script>

<template>
  <div class="layout">
    <EmployeeAside active="list" />
    <main class="main">
      <h2>我的工单</h2>
      <div class="filters">
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 140px" @change="load">
          <el-option v-for="(label, value) in statusLabel" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.category" clearable placeholder="类别" style="width: 140px" @change="load">
          <el-option v-for="(label, value) in categoryLabel" :key="value" :label="label" :value="value" />
        </el-select>
      </div>
      <el-table
        v-loading="loading"
        :data="rows"
        empty-text="还没有工单"
        style="cursor: pointer"
        @row-click="(row) => router.push(`/employee/tickets/${row.id}`)"
      >
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
        <template #empty>
          <el-empty description="还没有工单" />
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
