<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteKbArticle,
  getKbIngestJob,
  ingestKbFile,
  listKbArticles,
  listKbIngestJobs
} from '@/api/kb'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const router = useRouter()
const loading = ref(false)
const deletingId = ref(null)
const rows = ref([])
const jobs = ref([])
const uploading = ref(false)
const pollTimer = ref(null)
const filters = reactive({
  category: '',
  q: ''
})
const ingest = reactive({
  category: 'account',
  title: '',
  enableOcr: false,
  file: null
})

const categoryLabel = {
  account: '账号',
  device: '设备',
  network: '网络',
  permission: '权限'
}

const statusLabel = {
  pending: '排队中',
  running: '处理中',
  succeeded: '成功',
  failed: '失败'
}

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.category) params.category = filters.category
    if (filters.q.trim()) params.q = filters.q.trim()
    const res = await listKbArticles(params)
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

const loadJobs = async () => {
  try {
    const res = await listKbIngestJobs({ limit: 8 })
    const body = res.data
    if (body.code !== 200) return
    jobs.value = body.data?.items || []
    const busy = jobs.value.some((j) => j.status === 'pending' || j.status === 'running')
    if (busy && !pollTimer.value) {
      pollTimer.value = setInterval(async () => {
        await loadJobs()
        const still = jobs.value.some((j) => j.status === 'pending' || j.status === 'running')
        if (!still) {
          clearInterval(pollTimer.value)
          pollTimer.value = null
          await load()
        }
      }, 2000)
    }
  } catch {
    /* 任务表未建时不挡列表 */
  }
}

const onFileChange = (uploadFile) => {
  ingest.file = uploadFile?.raw || null
}

const onUpload = async () => {
  if (!ingest.file) {
    ElMessage.warning('请选择 PDF / DOCX / MD / 图片')
    return
  }
  const fd = new FormData()
  fd.append('category', ingest.category)
  fd.append('file', ingest.file)
  if (ingest.title.trim()) fd.append('title', ingest.title.trim())
  fd.append('enable_ocr', ingest.enableOcr ? 'true' : 'false')

  uploading.value = true
  try {
    const res = await ingestKbFile(fd)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '提交失败')
      return
    }
    ElMessage.success(body.message || '已受理')
    ingest.file = null
    ingest.title = ''
    await loadJobs()
    const jobId = body.data?.job_id
    if (jobId) {
      // 再拉一次详情，便于立刻看到 pending
      try {
        await getKbIngestJob(jobId)
      } catch {
        /* ignore */
      }
    }
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '提交失败'))
  } finally {
    uploading.value = false
  }
}

const onDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」？`, '删除文章', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    const res = await deleteKbArticle(row.id)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '删除失败')
      return
    }
    ElMessage.success(body.message || '已删除')
    await load()
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '删除失败'))
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await load()
  await loadJobs()
})

onUnmounted(() => {
  if (pollTimer.value) clearInterval(pollTimer.value)
})
</script>

<template>
  <div class="layout">
    <SupportAside active="kb" />
    <main class="main">
      <div class="head">
        <h2>知识库</h2>
        <el-button type="primary" @click="router.push('/support/kb/edit')">新建文章</el-button>
      </div>

      <el-card class="ingest" shadow="never">
        <template #header>
          <span>文件入库（PDF / DOCX / MD / 图片）</span>
        </template>
        <div class="ingest-row">
          <el-select v-model="ingest.category" style="width: 140px">
            <el-option
              v-for="(label, value) in categoryLabel"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
          <el-input
            v-model="ingest.title"
            clearable
            placeholder="标题（可空，默认用文件名）"
            style="width: 220px"
          />
          <el-upload
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            accept=".md,.markdown,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp"
            @change="onFileChange"
            @remove="() => (ingest.file = null)"
          >
            <el-button>选择文件</el-button>
          </el-upload>
          <el-checkbox v-model="ingest.enableOcr">图片 OCR / 图意</el-checkbox>
          <el-button type="primary" :loading="uploading" @click="onUpload">提交入库</el-button>
        </div>
        <p class="hint">提交后接口先回「已受理」，后台解析切分再写向量；图片请勾选 OCR。</p>
        <el-table v-if="jobs.length" :data="jobs" size="small" class="job-table">
          <el-table-column prop="id" label="任务" width="70" />
          <el-table-column prop="filename" label="文件" min-width="140" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">{{ statusLabel[row.status] || row.status }}</template>
          </el-table-column>
          <el-table-column prop="chunk_count" label="块数" width="70" />
          <el-table-column prop="article_id" label="文章" width="80" />
          <el-table-column prop="error_message" label="失败原因" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-card>

      <div class="filters">
        <el-select v-model="filters.category" clearable placeholder="类别" style="width: 140px" @change="load">
          <el-option v-for="(label, value) in categoryLabel" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input
          v-model="filters.q"
          clearable
          placeholder="标题或正文关键字"
          style="width: 240px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-button @click="load">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" @row-click="(row) => router.push(`/support/kb/edit/${row.id}`)">
        <el-table-column prop="id" label="编号" width="80" />
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column label="类别" width="100">
          <template #default="{ row }">{{ categoryLabel[row.category] || row.category }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="180" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="router.push(`/support/kb/edit/${row.id}`)">
              编辑
            </el-button>
            <el-button
              type="danger"
              link
              :loading="deletingId === row.id"
              @click.stop="onDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有知识库文章" />
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
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.ingest {
  margin-bottom: 20px;
}
.ingest-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.hint {
  margin: 8px 0 0;
  color: #888;
  font-size: 13px;
}
.job-table {
  margin-top: 12px;
}
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
