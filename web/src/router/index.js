import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { requiresAuth: false, title: '注册' },
  },
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/chat/ChatView.vue'),
        meta: { title: '智能问答' },
      },
      {
        path: 'kb',
        name: 'KnowledgeBaseList',
        component: () => import('@/views/kb/KbListView.vue'),
        meta: { title: '知识库管理' },
      },
      {
        path: 'kb/:id',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/views/kb/KbDetailView.vue'),
        meta: { title: '知识库详情' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/user/ProfileView.vue'),
        meta: { title: '个人中心' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  const isLogin = !!userStore.token
  if (to.meta?.title) {
    document.title = `${to.meta.title} · 企业级 RAG 知识库`
  }
  if (to.meta.requiresAuth !== false && !isLogin) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  if ((to.name === 'Login' || to.name === 'Register') && isLogin) {
    return { name: 'Chat' }
  }
  return true
})

export default router
