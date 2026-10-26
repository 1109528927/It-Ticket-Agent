<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createSupportUser } from '@/api/user'
import { getErrorMessage } from '@/utils/request'
import SupportAside from '@/components/SupportAside.vue'

const formRef = ref()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  repassword: '',
  employee_no: ''
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' }
  ],
  repassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error('两次密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

const submit = async () => {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return

  loading.value = true
  try {
    const res = await createSupportUser({
      username: form.username.trim(),
      password: form.password,
      repassword: form.repassword,
      employee_no: form.employee_no?.trim() || undefined
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '开通失败')
      return
    }
    ElMessage.success(body.message || '开通成功')
    form.username = ''
    form.password = ''
    form.repassword = ''
    form.employee_no = ''
    formRef.value?.clearValidate()
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '开通失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="layout">
    <SupportAside active="create" />
    <main class="main">
      <h2>开通客服</h2>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
        class="form"
        @submit.prevent
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" maxlength="50" placeholder="登录账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="repassword">
          <el-input v-model="form.repassword" type="password" show-password placeholder="再输入一次" />
        </el-form-item>
        <el-form-item label="工号" prop="employee_no">
          <el-input v-model="form.employee_no" maxlength="50" placeholder="可空，空则自动生成" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">开通</el-button>
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
  max-width: 480px;
}
</style>
