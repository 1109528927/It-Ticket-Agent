<script setup>
import { useRouter } from 'vue-router'

defineProps({
  active: { type: String, default: 'list' }
})

const router = useRouter()
const user = JSON.parse(localStorage.getItem('userInfo') || '{}')

const onMenu = (index) => {
  if (index === 'list') router.push('/employee/tickets')
  if (index === 'create') router.push('/employee/tickets/create')
  if (index === 'assistant') router.push('/assistant')
}

const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  router.push('/login')
}
</script>

<template>
  <aside class="side">
    <div class="who">{{ user.username }}</div>
    <el-menu :default-active="active" class="menu" @select="onMenu">
      <el-menu-item index="list">我的工单</el-menu-item>
      <el-menu-item index="create">新建工单</el-menu-item>
      <el-menu-item index="assistant">助手</el-menu-item>
    </el-menu>
    <el-button class="logout" @click="logout">退出</el-button>
  </aside>
</template>

<style scoped>
.side {
  width: 200px;
  border-right: 1px solid #eee;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
}
.who {
  font-weight: 600;
  margin-bottom: 12px;
}
.menu {
  border-right: none;
  flex: 1;
}
.logout {
  margin-top: 12px;
}
</style>
