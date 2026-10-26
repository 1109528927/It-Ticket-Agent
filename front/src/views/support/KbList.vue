<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteKbArticle, listKbArticles } from '@/api/kb'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const router = useRouter()
const loading = ref(false)
const deletingId = ref(null)
const rows = ref([])
const filters = reactive({
  category: '',
  q: ''
})

const categoryLabel = {
  account: '账号',
  device: '设备',
  network: '网络',
  permission: '权限'
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

onMounted(load)
</script>

<template>
  <div class="layout">
    <SupportAside active="kb" />
    <main class="main">
      <div class="head">
        <h2>知识库</h2>
        <el-button type="primary" @click="router.push('/support/kb/edit')">新建文章</el-button>
      </div>
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
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
