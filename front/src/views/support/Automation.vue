<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAutomationConfig,
  getAutomationRun,
  listAutomationRuns,
  runBacklogJob,
  runSlaJob,
  saveAutomationConfig
} from '@/api/automation'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const activeTab = ref('settings')
const loading = ref(false)
const saving = ref(false)
const batching = ref(false)
const slaRunning = ref(false)
const runs = ref([])
const detail = ref(null)
const configLoaded = ref(false)

const form = reactive({
  enable_backlog_draft: true,
  enable_sla_sweep: true,
  enable_triage_on_create: true,
  backlog_schedule_mode: 'interval',
  backlog_interval_minutes: 60,
  backlog_daily_time: '02:00',
  sla_interval_minutes: 15,
  skip_high_risk: false,
  auto_send_simple_reply: false,
  backlog_categories: []
})

const meta = reactive({
  last_backlog_run_at: null,
  last_sla_run_at: null,
  cron_expression: null,
  updated_at: null
})

const categoryOptions = [
  { value: 'account', label: '账号' },
  { value: 'network', label: '网络' },
  { value: 'device', label: '设备' },
  { value: 'permission', label: '权限' }
]

const jobTypeLabel = {
  backlog_draft: '积压单智能起草',
  sla_sweep: '超时工单巡检'
}

const triggerLabel = {
  manual: '手动触发',
  cron: '定时自动'
}

const actionLabel = {
  draft_reply: '生成回复草稿',
  draft_reply_skip_risk: '高危跳过（等白班）',
  auto_reply: '简单单已自动回复',
  sla_unclaimed: '催办未认领',
  sla_unclaimed_skip: '未认领（已催过）',
  sla_confirm_timeout: '催办待确认超时',
  sla_confirm_skip: '待确认（已催过）'
}

const formatTime = (v) => {
  if (!v) return '尚未执行'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v).replace('T', ' ').slice(0, 19)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const statusText = (row) => {
  if (row.status === 'running') return '进行中'
  if (row.status === 'failed') return '执行失败'
  const failed = row.summary?.failed ?? 0
  if (failed > 0) return '部分失败'
  return '执行成功'
}

const summarize = (row) => {
  if (row.error_message) {
    if (String(row.error_message).includes('AttributeError')) {
      return '旧版本程序异常，请重新点一次「立即执行」'
    }
    return '任务失败，请稍后重试或联系管理员'
  }
  const s = row.summary
  if (!s) return '—'
  const scanned = s.scanned ?? 0
  const ok = s.ok ?? 0
  const failed = s.failed ?? 0
  if (row.job_type === 'sla_sweep') {
    return `共巡检 ${scanned} 条，成功 ${ok} 条` + (failed ? `，失败 ${failed} 条` : '')
  }
  return (
    `共扫描 ${scanned} 单，成功处理 ${ok} 单` +
    (failed ? `，${failed} 单失败` : '') +
    '（简单单可自动回复，高危仅起草）'
  )
}

const scheduleHint = computed(() => {
  if (form.backlog_schedule_mode === 'daily') {
    return `每天 ${form.backlog_daily_time || '02:00'} 自动起草一次（维护夜可先关掉开关）`
  }
  return `大约每 ${form.backlog_interval_minutes || 60} 分钟自动扫一轮积压单`
})

const applyConfig = (data) => {
  if (!data) return
  form.enable_backlog_draft = !!data.enable_backlog_draft
  form.enable_sla_sweep = !!data.enable_sla_sweep
  form.enable_triage_on_create = !!data.enable_triage_on_create
  form.backlog_schedule_mode = data.backlog_schedule_mode || 'interval'
  form.backlog_interval_minutes = data.backlog_interval_minutes || 60
  form.backlog_daily_time = (data.backlog_daily_time || '02:00').slice(0, 5)
  form.sla_interval_minutes = data.sla_interval_minutes || 15
  form.skip_high_risk = !!data.skip_high_risk
  form.auto_send_simple_reply = !!data.auto_send_simple_reply
  form.backlog_categories = Array.isArray(data.backlog_categories)
    ? [...data.backlog_categories]
    : []
  meta.last_backlog_run_at = data.last_backlog_run_at
  meta.last_sla_run_at = data.last_sla_run_at
  meta.cron_expression = data.cron_expression
  meta.updated_at = data.updated_at
  configLoaded.value = true
}

const loadConfig = async () => {
  try {
    const res = await getAutomationConfig()
    applyConfig(res.data?.data)
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载自动化设置失败'))
  }
}

const onSave = async () => {
  saving.value = true
  try {
    const res = await saveAutomationConfig({ ...form })
    applyConfig(res.data?.data)
    ElMessage.success('设置已保存，定时任务会按新配置执行')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

const loadRuns = async () => {
  loading.value = true
  try {
    const res = await listAutomationRuns(40)
    runs.value = res.data?.data?.items || []
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载执行记录失败'))
  } finally {
    loading.value = false
  }
}

const openRun = async (id) => {
  try {
    const res = await getAutomationRun(id)
    detail.value = res.data?.data || null
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载明细失败'))
  }
}

const onBatch = async () => {
  batching.value = true
  try {
    const res = await runBacklogJob()
    const data = res.data?.data || {}
    const failed = data.failed ?? 0
    const scanned = data.scanned ?? 0
    const ok = data.ok ?? 0
    if (failed > 0) {
      ElMessage.warning(
        `已跑完：共扫描 ${scanned} 单，成功生成草稿 ${ok} 单，${failed} 单处理失败`
      )
    } else {
      ElMessage.success(`已跑完：共扫描 ${scanned} 单，成功生成草稿 ${ok} 单`)
    }
    await loadRuns()
    await loadConfig()
    activeTab.value = 'logs'
    if (data.run_id) await openRun(data.run_id)
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '执行失败，请稍后重试'))
  } finally {
    batching.value = false
  }
}

const onSla = async () => {
  slaRunning.value = true
  try {
    const res = await runSlaJob()
    const data = res.data?.data || {}
    ElMessage.success(`催办巡检完成：共处理 ${data.scanned ?? 0} 条`)
    await loadRuns()
    await loadConfig()
    activeTab.value = 'logs'
    if (data.run_id) await openRun(data.run_id)
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '催办巡检失败，请稍后重试'))
  } finally {
    slaRunning.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadConfig(), loadRuns()])
})
</script>

<template>
  <div class="layout">
    <SupportAside active="automation" />
    <main class="main">
      <h2>工单自动化</h2>
      <p class="hint">
        每位客服都能用：可以开关自动起草、超时催办，改执行节奏和类别策略。
        夜班可开「简单单自动回复」；高危只起草等白班，不会自动改密或结案。关掉总开关后定时任务会静默跳过。
      </p>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="自动化设置" name="settings">
          <el-form v-loading="!configLoaded" label-width="160px" class="settings-form">
            <el-form-item label="积压单智能起草">
              <el-switch
                v-model="form.enable_backlog_draft"
                active-text="开启"
                inactive-text="关闭"
              />
            </el-form-item>
            <el-form-item label="超时工单巡检">
              <el-switch
                v-model="form.enable_sla_sweep"
                active-text="开启"
                inactive-text="关闭"
              />
            </el-form-item>
            <el-form-item label="建单后自动初审">
              <el-switch
                v-model="form.enable_triage_on_create"
                active-text="开启"
                inactive-text="关闭"
              />
            </el-form-item>

            <el-divider content-position="left">起草节奏</el-divider>
            <el-form-item label="怎么定时">
              <el-radio-group v-model="form.backlog_schedule_mode">
                <el-radio value="interval">每隔一段时间</el-radio>
                <el-radio value="daily">每天固定时刻（适合夜间批跑）</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item
              v-if="form.backlog_schedule_mode === 'interval'"
              label="每隔多少分钟"
            >
              <el-input-number
                v-model="form.backlog_interval_minutes"
                :min="5"
                :max="1440"
                :step="5"
              />
              <span class="unit">分钟</span>
            </el-form-item>
            <el-form-item v-else label="每天执行时刻">
              <el-time-select
                v-model="form.backlog_daily_time"
                start="00:00"
                step="00:30"
                end="23:30"
                placeholder="选择时间"
              />
            </el-form-item>
            <el-form-item label="催办巡检间隔">
              <el-input-number
                v-model="form.sla_interval_minutes"
                :min="5"
                :max="1440"
                :step="5"
              />
              <span class="unit">分钟</span>
            </el-form-item>
            <p class="schedule-hint">{{ scheduleHint }}</p>

            <el-divider content-position="left">策略与风险</el-divider>
            <el-form-item label="只对这些类别起草">
              <el-checkbox-group v-model="form.backlog_categories">
                <el-checkbox
                  v-for="opt in categoryOptions"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </el-checkbox>
              </el-checkbox-group>
              <p class="field-tip">不勾选表示全部类别；例如只勾「账号」「网络」，设备类就不会自动起草。</p>
            </el-form-item>
            <el-form-item label="高危单处理">
              <el-switch
                v-model="form.skip_high_risk"
                active-text="直接跳过"
                inactive-text="仍生成草稿并标红提示"
              />
            </el-form-item>
            <el-form-item label="简单单自动回复">
              <el-switch
                v-model="form.auto_send_simple_reply"
                active-text="开启（适合夜班无人值守）"
                inactive-text="关闭（只起草）"
              />
              <p class="field-tip" style="margin: 8px 0 0">
                开启后：非高危单起草完会自动写成正式回复并留审计记录；含改密/改权语义的单仍只起草，等白班处理。不会自动确认高危、不会自动结案。
              </p>
            </el-form-item>

            <el-form-item label="上次起草">
              <span>{{ formatTime(meta.last_backlog_run_at) }}</span>
            </el-form-item>
            <el-form-item label="上次催办巡检">
              <span>{{ formatTime(meta.last_sla_run_at) }}</span>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="onSave">
                保存设置
              </el-button>
              <el-button :loading="batching" @click="onBatch">立即执行一次起草</el-button>
              <el-button :loading="slaRunning" @click="onSla">立即执行一次催办巡检</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="执行记录" name="logs">
          <div class="toolbar">
            <el-button type="primary" :loading="batching" @click="onBatch">
              立即执行一次起草
            </el-button>
            <el-button :loading="slaRunning" @click="onSla">立即执行一次催办巡检</el-button>
            <el-button :loading="loading" @click="loadRuns">刷新</el-button>
          </div>

          <el-table
            v-loading="loading"
            :data="runs"
            stripe
            style="width: 100%"
            @row-click="(row) => openRun(row.id)"
          >
            <el-table-column prop="id" label="编号" width="70" />
            <el-table-column label="任务" min-width="150">
              <template #default="{ row }">
                {{ jobTypeLabel[row.job_type] || row.job_type }}
              </template>
            </el-table-column>
            <el-table-column label="触发方式" width="110">
              <template #default="{ row }">
                {{ triggerLabel[row.trigger_source] || row.trigger_source }}
              </template>
            </el-table-column>
            <el-table-column label="结果" width="110">
              <template #default="{ row }">
                {{ statusText(row) }}
              </template>
            </el-table-column>
            <el-table-column label="摘要" min-width="260">
              <template #default="{ row }">
                <span :class="{ err: row.status === 'failed' || (row.summary?.failed > 0) }">
                  {{ summarize(row) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="160">
              <template #default="{ row }">
                {{ formatTime(row.started_at) }}
              </template>
            </el-table-column>
          </el-table>

          <section v-if="detail" class="detail">
            <h3>第 {{ detail.id }} 次 · 明细</h3>
            <p class="meta-line">
              {{ jobTypeLabel[detail.job_type] || detail.job_type }}
              ·
              {{ statusText(detail) }}
              ·
              {{ triggerLabel[detail.trigger_source] || detail.trigger_source }}
            </p>
            <el-table :data="detail.results || []" size="small" stripe>
              <el-table-column label="工单号" width="90">
                <template #default="{ row }">#{{ row.ticket_id }}</template>
              </el-table-column>
              <el-table-column label="做了什么" width="150">
                <template #default="{ row }">
                  {{ actionLabel[row.action] || row.action }}
                </template>
              </el-table-column>
              <el-table-column label="是否成功" width="90">
                <template #default="{ row }">
                  {{ row.success ? '成功' : '失败' }}
                </template>
              </el-table-column>
              <el-table-column label="说明" min-width="280">
                <template #default="{ row }">
                  {{
                    String(row.detail || '').includes('AttributeError')
                      ? '旧版本程序异常，请重新执行'
                      : row.detail || '—'
                  }}
                </template>
              </el-table-column>
            </el-table>
            <p class="tip">到对应工单处理页，可用「采用助手草稿」把生成的回复填进输入框。</p>
          </section>
        </el-tab-pane>
      </el-tabs>
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
  max-width: 1100px;
}
.hint {
  color: #666;
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 12px;
}
.settings-form {
  max-width: 720px;
  margin-top: 8px;
}
.unit {
  margin-left: 8px;
  color: #666;
}
.schedule-hint,
.field-tip {
  margin: -8px 0 16px 160px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.err {
  color: #f56c6c;
}
.detail {
  margin-top: 28px;
}
.meta-line {
  color: #888;
  font-size: 13px;
}
.tip {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
}
</style>
