<template>
  <div class="main-layout">
    <aside class="sidebar">
      <div class="logo-area">
        <span class="logo">🧠</span>
        <span class="brand">RAG KB</span>
      </div>
      <nav class="nav-list">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="nav-item--active"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-text">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <el-dropdown trigger="click" @command="handleUserCmd">
          <div class="user-block">
            <el-avatar :size="36" style="background: var(--app-primary); color: #fff; font-weight: 700">
              {{ avatarChar }}
            </el-avatar>
            <div class="user-info">
              <div class="user-name">{{ userStore.user?.nickname || userStore.user?.username || '用户' }}</div>
              <div class="user-role">{{ userStore.user?.is_superuser ? '管理员' : '普通用户' }}</div>
            </div>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </aside>

    <div class="main-area">
      <header class="top-header">
        <div class="header-title">{{ pageTitle }}</div>
        <div class="header-right">
          <slot name="header-actions"></slot>
        </div>
      </header>
      <main class="content-area">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/chat', label: '智能问答', icon: '💬' },
  { path: '/kb', label: '知识库管理', icon: '📚' },
  { path: '/profile', label: '个人中心', icon: '👤' },
]

const pageTitle = computed(() => route.meta?.title || '')
const avatarChar = computed(() => {
  const name = userStore.user?.nickname || userStore.user?.username || 'U'
  return name.slice(0, 1).toUpperCase()
})

function handleUserCmd(cmd) {
  if (cmd === 'profile') router.push('/profile')
  if (cmd === 'logout') {
    ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
      .then(() => {
        userStore.logout()
        ElMessage.success('已退出')
        router.replace('/login')
      })
      .catch(() => {})
  }
}
</script>

<style lang="scss" scoped>
.main-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--app-sidebar-bg);
  border-right: 1px solid var(--app-border-color);
  display: flex;
  flex-direction: column;
  .logo-area {
    height: 64px;
    padding: 0 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid var(--app-border-color);
    .logo {
      font-size: 28px;
    }
    .brand {
      font-size: 18px;
      font-weight: 800;
      background: linear-gradient(135deg, #4f46e5, #06b6d4);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
  }
  .nav-list {
    flex: 1;
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 10px;
    color: var(--app-text-muted);
    transition: all 0.2s ease;
    font-size: 14px;
    font-weight: 500;
    &:hover {
      background: var(--app-bg-color);
      color: var(--app-text-color);
    }
    &--active {
      background: var(--app-primary-light);
      color: var(--app-primary);
      font-weight: 700;
    }
    .nav-icon {
      font-size: 18px;
    }
  }
  .sidebar-footer {
    padding: 16px;
    border-top: 1px solid var(--app-border-color);
  }
  .user-block {
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 6px;
    border-radius: 8px;
    &:hover {
      background: var(--app-bg-color);
    }
    .user-info {
      flex: 1;
      min-width: 0;
      .user-name {
        font-weight: 600;
        font-size: 14px;
        line-height: 1.4;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .user-role {
        font-size: 12px;
        color: var(--app-text-muted);
        margin-top: 2px;
      }
    }
  }
}
.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.top-header {
  height: 64px;
  flex-shrink: 0;
  background: var(--app-header-bg);
  border-bottom: 1px solid var(--app-border-color);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  .header-title {
    font-size: 18px;
    font-weight: 700;
  }
}
.content-area {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px;
}
</style>
