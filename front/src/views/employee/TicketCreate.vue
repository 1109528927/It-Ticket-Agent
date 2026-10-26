<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createTicket } from '@/api/ticket'
import { getErrorMessage } from '@/utils/request'
import EmployeeAside from '@/components/EmployeeAside.vue'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  category: 'account',
  title: '',
  description: '',
  priority: 'medium'
})

const rules = {
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
  title: [
    { required: true, message: '请输入标题', trigger: 'blur' },
    { min: 1, max: 200, message: '标题 1～200 字', trigger: 'blur' }
  ],
  description: [{ required: true, message: '请输入描述', trigger: 'blur' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }]
}

const submit = async () => {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return

  loading.value = true
  try {
    const res = await createTicket({
      category: form.category,
      title: form.title.trim(),
      description: form.description.trim(),
      priority: form.priority
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '创建失败')
      return
    }
    ElMessage.success(body.message || '创建成功')
    router.push('/employee/tickets')
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '创建失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="layout">
    <EmployeeAside active="create" />
    <main class="main">
      <h2>新建工单</h2>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="88px"
        class="form"
        @submit.prevent
      >
        <el-form-item label="类别" prop="category">
          <el-select v-model="form.category" style="width: 220px">
            <el-option label="账号" value="account" />
            <el-option label="设备" value="device" />
            <el-option label="网络" value="network" />
            <el-option label="权限" value="permission" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="一句话说清问题" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="5"
            placeholder="补充现象、时间和影响"
          />
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-radio-group v-model="form.priority">
            <el-radio value="low">低</el-radio>
            <el-radio value="medium">中</el-radio>
            <el-radio value="high">高</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">提交</el-button>
          <el-button @click="router.push('/employee/tickets')">取消</el-button>
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
  max-width: 640px;
}
</style>
