<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
const user = JSON.parse(localStorage.getItem('userInfo') || '{}')

const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  router.push('/login')
}
</script>

<template>
  <div class="page">
    <h2>员工工作台</h2>
    <p>{{ user.username }}，工号 {{ user.employee_no }}。工单功能下一步再做。</p>
    <el-button @click="logout">退出</el-button>
  </div>
</template>

<style scoped>
.page {
  padding: 32px;
}
</style>
