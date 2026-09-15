<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo">🤖</div>
        <h2>企业级 RAG 知识库</h2>
        <p>登录后即可构建您的专属智能问答知识库</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="login-form">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" size="large" show-password />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleSubmit">
          登录
        </el-button>
        <div class="footer-link">
          <span>还没有账号？</span>
          <router-link :to="{ name: 'Register' }">立即注册</router-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    loading.value = true
    await userStore.login(form)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/chat'
    router.replace(redirect)
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 50%, #ecfeff 100%);
  padding: 24px;
}
.login-card {
  width: 100%;
  max-width: 420px;
  background: var(--app-card-bg);
  border-radius: 16px;
  padding: 40px 36px;
  box-shadow: 0 20px 40px -12px rgba(15, 23, 42, 0.15);
}
.login-header {
  text-align: center;
  margin-bottom: 28px;
  .logo {
    font-size: 44px;
    line-height: 1;
    margin-bottom: 12px;
  }
  h2 {
    font-size: 24px;
    margin: 0 0 6px;
    font-weight: 700;
  }
  p {
    margin: 0;
    color: var(--app-text-muted);
    font-size: 14px;
  }
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
  height: 44px;
  font-weight: 600;
}
.footer-link {
  margin-top: 16px;
  text-align: center;
  font-size: 14px;
  color: var(--app-text-muted);
  a {
    color: var(--app-primary);
    font-weight: 600;
    margin-left: 4px;
  }
}
</style>
