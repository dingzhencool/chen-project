import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMeApi, loginApi, registerApi } from '@/api/auth'

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
  }

  async function login(params) {
    const res = await loginApi(params)
    token.value = res.data.access_token
    user.value = res.data.user
    saveToLocal()
    return res.data
  }

  async function register(params) {
    const res = await registerApi(params)
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
