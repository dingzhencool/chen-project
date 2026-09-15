<template>
  <div class="register-page">
    <div class="register-card">
      <div class="register-header">
        <div class="logo">📚</div>
        <h2>创建新账号</h2>
        <p>开启您的企业级 RAG 智能知识库之旅</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="register-form">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="3-64 位字符" size="large" />
        </el-form-item>
        <el-form-item label="邮箱（选填）" prop="email">
          <el-input v-model="form.email" placeholder="example@company.com" size="large" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="至少 6 位" size="large" show-password />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleSubmit">
          注册并登录
        </el-button>
        <div class="footer-link">
          <span>已有账号？</span>
          <router-link :to="{ name: 'Login' }">立即登录</router-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '' })
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '用户名长度 3-64 位', trigger: 'blur' },
  ],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
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
    await userStore.register(form)
    ElMessage.success('注册成功')
    router.replace('/chat')
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fef3c7 0%, #fff7ed 50%, #ecfeff 100%);
  padding: 24px;
}
.register-card {
  width: 100%;
  max-width: 440px;
  background: var(--app-card-bg);
  border-radius: 16px;
  padding: 40px 36px;
  box-shadow: 0 20px 40px -12px rgba(15, 23, 42, 0.15);
}
.register-header {
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
