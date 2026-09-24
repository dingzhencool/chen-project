import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMeApi, loginApi, registerApi } from '@/api/auth'
import { useChatStore } from '@/stores/chat'
import { useKbStore } from '@/stores/knowledgeBase'

export const useUserStore = defineStore('user', () => {
  const token = ref('')
  const user = ref(null)

  function saveToLocal() {
    if (token.value) localStorage.setItem('token', token.value)
    if (user.value) localStorage.setItem('user', JSON.stringify(user.value))
  }

  function restoreFromLocal() {
    const t = localStorage.getItem('token')
    const u = localStorage.getItem('user')
    if (t) token.value = t
    if (u) {
      try {
        user.value = JSON.parse(u)
      } catch (e) {
        user.value = null
      }
    }
  }

  function clearAll() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    // 切换/退出账号时必须同步清空其他 store 的业务数据，
    // 防止前一用户的会话/知识库内容残留并显示给下一用户（隐私隔离）
    useChatStore().reset()
    useKbStore().reset()
  }

  async function login(params) {
    const res = await loginApi(params)
    // 若已登录过其他账号，先清旧账号的会话/知识库数据，避免新旧账号数据混杂
    if (token.value) clearAll()
    token.value = res.data.access_token
    user.value = res.data.user
    saveToLocal()
    return res.data
  }

  async function register(params) {
    const res = await registerApi(params)
    if (token.value) clearAll()
    token.value = res.data.access_token
    user.value = res.data.user
    saveToLocal()
    return res.data
  }

  async function fetchMe() {
    const res = await getMeApi()
    user.value = res.data
    saveToLocal()
    return res.data
  }

  function logout() {
    clearAll()
  }

  return {
    token,
    user,
    login,
    register,
    fetchMe,
    logout,
    restoreFromLocal,
    clearAll,
  }
})
