<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import router from '@/router'
import request, { getErrorMessage } from '@/utils/request'

const isLogin = ref(true)
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
  repassword: '',
  employee_no: ''
})

const toggleMode = () => {
  isLogin.value = !isLogin.value
  form.password = ''
  form.repassword = ''
}

const goHome = (user) => {
  router.push(user?.role === 'support' ? '/support/home' : '/employee/home')
}

const login = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const res = await request({
      url: '/api/user/login',
      method: 'post',
      data: {
        username: form.username,
        password: form.password
      }
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '登录失败')
      return
    }
    localStorage.setItem('token', body.data.token)
    localStorage.setItem('userInfo', JSON.stringify(body.data.user))
    ElMessage.success(body.message || '登录成功')
    goHome(body.data.user)
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '登录失败'))
  } finally {
    loading.value = false
  }
}

const register = async () => {
  if (!form.username?.trim() || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  if (form.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  if (!form.repassword) {
    ElMessage.warning('请再次输入确认密码')
    return
  }
  if (form.password !== form.repassword) {
    ElMessage.warning('两次密码不一致')
    return
  }
  loading.value = true
  try {
    const res = await request({
      url: '/api/user/register',
      method: 'post',
      data: {
        username: form.username.trim(),
        password: form.password,
        repassword: form.repassword,
        employee_no: form.employee_no?.trim() || undefined
      }
    })
    const body = res.data
    if (body.code !== 200) {
      ElMessage.error(body.message || '注册失败')
      return
    }
    ElMessage.success(body.message || '注册成功，请登录')
    isLogin.value = true
    form.password = ''
    form.repassword = ''
  } catch (e) {
    ElMessage.error(getErrorMessage(e, '注册失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="box">
      <h3>内部 IT 工单台</h3>
      <p class="sub">{{ isLogin ? '登录' : '员工注册' }}</p>
      <el-form v-if="isLogin">
        <el-form-item>
          <el-input
            v-model="form.username"
            size="large"
            placeholder="请输入账号"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="login"
          />
        </el-form-item>
        <el-button
          size="large"
          type="primary"
          style="width: 100%"
          :loading="loading"
          @click="login"
        >
          登 录
        </el-button>
        <div style="text-align: right; margin-top: 20px">
          <a href="#" @click.prevent="toggleMode">还没有账号？注册员工</a>
        </div>
      </el-form>

      <el-form v-else>
        <el-form-item>
          <el-input
            v-model="form.username"
            size="large"
            placeholder="请输入注册账号"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.employee_no" size="large" placeholder="工号（可空，自动生成）" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            placeholder="请输入注册密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.repassword"
            type="password"
            size="large"
            placeholder="请重新输入注册密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-button
          size="large"
          type="primary"
          style="width: 100%"
          :loading="loading"
          @click="register"
        >
          注 册
        </el-button>
        <div style="text-align: right; margin-top: 20px">
          <a href="#" @click.prevent="toggleMode">已有账号？请登录</a>
        </div>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(160deg, #e8f5f0 0%, #f5f7fa 45%, #eef2f7 100%);
}
.box {
  width: 380px;
  padding: 32px 28px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  text-align: center;
}
.box h3 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}
.sub {
  margin: 8px 0 24px;
  color: #606266;
}
.box a {
  color: var(--el-color-primary);
  text-decoration: none;
  cursor: pointer;
  font-size: 14px;
}
.box a:hover {
  text-decoration: underline;
}
</style>
