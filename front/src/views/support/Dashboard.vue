<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDashboardStats } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const loading = ref(false)
const stats = ref({
  today_created: 0,
  night_auto_resolved: 0,
  draft_adopt_rate: 0,
  overdue_unhandled: 0
})

const load = async () => {
  loading.value = true
  try {
    const res = await getDashboardStats()
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '加载失败')
      return
    }
    stats.value = body.data || stats.value
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const pct = (v) => `${(Number(v || 0) * 100).toFixed(1)}%`

onMounted(load)
</script>

<template>
  <div class="layout">
    <SupportAside active="dashboard" />
    <main class="main" v-loading="loading">
      <h2>数据大盘</h2>
      <p class="hint">看夜间自动结案与白天一键执行是否真在降本。</p>
      <div class="cards">
        <el-card shadow="hover">
          <div class="label">今日新增</div>
          <div class="num">{{ stats.today_created }}</div>
        </el-card>
        <el-card shadow="hover">
          <div class="label">夜间自动结案（累计 auto_resolved）</div>
          <div class="num">{{ stats.night_auto_resolved }}</div>
        </el-card>
        <el-card shadow="hover">
          <div class="label">今日一键执行率</div>
          <div class="num">{{ pct(stats.draft_adopt_rate) }}</div>
        </el-card>
        <el-card shadow="hover">
          <div class="label">超时/升级未处理</div>
          <div class="num warn">{{ stats.overdue_unhandled }}</div>
        </el-card>
      </div>
      <el-button class="refresh" @click="load">刷新</el-button>
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
.hint {
  color: #666;
  margin-bottom: 20px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
.label {
  color: #666;
  font-size: 14px;
  margin-bottom: 8px;
}
.num {
  font-size: 32px;
  font-weight: 700;
}
.num.warn {
  color: #c45656;
}
.refresh {
  margin-top: 20px;
}
</style>
