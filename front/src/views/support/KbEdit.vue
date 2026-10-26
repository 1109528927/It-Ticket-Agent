<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createKbArticle, getKbArticle, updateKbArticle } from '@/api/kb'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const saving = ref(false)
const articleId = route.params.id ? Number(route.params.id) : null
const isEdit = Boolean(articleId)

const form = reactive({
  category: 'account',
  title: '',
  content: ''
})

const rules = {
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入正文', trigger: 'blur' }]
}

const categoryLabel = {
  account: '账号',
  device: '设备',
  network: '网络',
  permission: '权限'
}

const load = async () => {
  if (!isEdit) return
  loading.value = true
  try {
    const res = await getKbArticle(articleId)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '加载失败')
      return
    }
    form.category = body.data.category
    form.title = body.data.title
    form.content = body.data.content
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '加载失败'))
    if (e?.response?.status === 404) {
      router.push('/support/kb')
    }
  } finally {
    loading.value = false
  }
}

const submit = async () => {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return

  saving.value = true
  try {
    const payload = {
      category: form.category,
      title: form.title.trim(),
      content: form.content.trim()
    }
    const res = isEdit
      ? await updateKbArticle(articleId, payload)
      : await createKbArticle(payload)
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '保存失败')
      return
    }
    ElMessage.success(body.message || '保存成功')
    router.push('/support/kb')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="layout">
    <SupportAside active="kb" />
    <main class="main" v-loading="loading">
      <h2>{{ isEdit ? '编辑文章' : '新建文章' }}</h2>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
        class="form"
        @submit.prevent
      >
        <el-form-item label="类别" prop="category">
          <el-select v-model="form.category" style="width: 200px">
            <el-option
              v-for="(label, value) in categoryLabel"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="200" placeholder="处理步骤标题" />
        </el-form-item>
        <el-form-item label="正文" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="12"
            placeholder="按步骤写清怎么处理"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
          <el-button @click="router.push('/support/kb')">返回列表</el-button>
        </el-form-item>
      </el-form>
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
.form {
  max-width: 720px;
}
</style>
