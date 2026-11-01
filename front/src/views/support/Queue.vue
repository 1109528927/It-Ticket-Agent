<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
const user = JSON.parse(localStorage.getItem('userInfo') || '{}')
const isSimpleDesk = computed(() => user.username === 'simple_desk')

const filters = reactive({
  scope: isSimpleDesk.value ? 'simple_desk' : '',
  status: '',
  lane: isSimpleDesk.value ? 'rag_ready' : 'all'
})

const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  pending_confirm: '待确认',
  waiting_feedback: '等反馈',
  auto_resolved: '夜间自动结案',
  need_manual: '需人工',
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
    if (filters.lane && filters.lane !== 'all') params.lane = filters.lane
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
  // 专席不认领：非高危应由批跑自动挂到 simple_desk
  if (isSimpleDesk.value) {
    ElMessage.info('简单单专席无需认领：非高危由批跑自动认领并起草，请到「RAG可直接回 / 需核对」处理')
    return
  }
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
    router.push(`/support/tickets/${row.id}`)
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

const rowClassName = ({ row }) => {
  if (row.escalate === 1 || row.status === 'need_manual') return 'row-escalate'
  if (row.rag_ready) return 'row-rag-ready'
  if (row.awaiting_adopt) return 'row-await-adopt'
  return ''
}

const actionLabel = (row) => {
  if (row.rag_ready) return '直接回复'
  if (row.awaiting_adopt) return '核对草稿'
  if (row.status === 'waiting_feedback') return '跟踪'
  return '处理'
}

watch(
  () => filters.lane,
  () => {
    if (filters.lane && filters.lane !== 'all') {
      filters.scope = 'simple_desk'
      filters.status = ''
    }
    load()
  }
)

onMounted(load)
</script>

<template>
  <div class="layout">
    <SupportAside active="queue" />
    <main class="main">
      <div class="page-head">
        <h2>{{ isSimpleDesk ? '简单单专席工作台' : '工单池' }}</h2>
      </div>

      <p v-if="isSimpleDesk" class="pool-hint">
        非高危自动进专席并起草。RAG 高置信进「可直接回」，一键发送后到「等反馈跟踪」标记解决。
      </p>
      <p v-else class="pool-hint">
        未认领含高危待认领；简单单在专席账号下处理。侧栏可进数据大盘与自动化。
      </p>

      <el-tabs v-model="filters.lane" class="desk-tabs">
        <el-tab-pane label="RAG 可直接回" name="rag_ready" />
        <el-tab-pane label="需核对草稿" name="need_review" />
        <el-tab-pane label="等反馈跟踪" name="tracking" />
        <el-tab-pane label="全部筛选" name="all" />
      </el-tabs>

      <div v-if="filters.lane === 'all'" class="filters">
        <el-select v-model="filters.scope" clearable placeholder="认领" style="width: 200px" @change="load">
          <el-option label="未认领（含高危待认领）" value="unclaimed" />
          <el-option v-if="!isSimpleDesk" label="我认领的" value="mine" />
          <el-option label="简单单专席（非高危）" value="simple_desk" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 160px" @change="load">
          <el-option v-for="(label, value) in statusLabel" :key="value" :label="label" :value="value" />
        </el-select>
      </div>

      <el-table v-loading="loading" :data="rows" :row-class-name="rowClassName">
        <el-table-column prop="id" label="编号" width="80" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="类别" width="100">
          <template #default="{ row }">{{ categoryLabel[row.category] || row.category }}</template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <span>{{ statusLabel[row.status] || row.status }}</span>
            <el-tag v-if="row.rag_ready" size="small" type="success" class="tag-gap">RAG可回</el-tag>
            <el-tag v-else-if="row.awaiting_adopt" size="small" type="warning" class="tag-gap">待核对</el-tag>
            <el-tag v-if="row.high_risk_hint" size="small" type="danger" class="tag-gap">高危</el-tag>
            <el-tag v-if="row.escalate === 1" size="small" type="danger" class="tag-gap">升级</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            <span v-if="row.draft_confidence != null">{{ Number(row.draft_confidence).toFixed(2) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">{{ priorityLabel[row.priority] || row.priority }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending' && !isSimpleDesk"
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
                {{ actionLabel(row) }}
              </el-button>
              <el-button
                v-if="row.status === 'waiting_feedback' || row.status === 'processing' || row.status === 'need_manual'"
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
          <el-empty
            :description="
              filters.lane === 'rag_ready'
                ? '暂无 RAG 高置信待回单（置信度需达到自动化门槛，可先跑批起草）'
                : filters.lane === 'need_review'
                  ? '暂无需核对的草稿'
                  : filters.lane === 'tracking'
                    ? '暂无等反馈跟踪的单'
                    : '当前筛选下没有工单'
            "
          />
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
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.page-head h2 {
  margin: 0;
}
.desk-tabs {
  margin-bottom: 8px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.pool-hint {
  margin: 0 0 12px;
  color: #666;
  font-size: 13px;
  line-height: 1.5;
}
.tag-gap {
  margin-left: 6px;
}
.muted {
  color: #999;
  font-size: 12px;
}
:deep(.row-rag-ready) {
  background: #f0f9eb;
}
:deep(.row-await-adopt) {
  background: #fffbeb;
}
:deep(.row-escalate) {
  background: #fff1f0;
}
</style>
