<script setup>
import { useRouter } from 'vue-router'

defineProps({
  active: { type: String, default: 'queue' }
})

const router = useRouter()
const user = JSON.parse(localStorage.getItem('userInfo') || '{}')

const onMenu = (index) => {
  if (index === 'queue') router.push('/support/queue')
  if (index === 'kb') router.push('/support/kb')
  if (index === 'assistant') router.push('/assistant')
  if (index === 'create') router.push('/support/users/create')
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
      <el-menu-item index="queue">工单池</el-menu-item>
      <el-menu-item index="kb">知识库</el-menu-item>
      <el-menu-item index="assistant">助手</el-menu-item>
      <el-menu-item index="create">开通客服</el-menu-item>
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
