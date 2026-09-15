<template>
  <div class="profile-page">
    <el-row :gutter="20">
      <el-col :xs="24" :md="8">
        <el-card shadow="never" class="profile-card">
          <div class="avatar-block">
            <el-avatar :size="96" style="background: var(--app-primary); color: #fff; font-size: 32px; font-weight: 700">
              {{ avatarChar }}
            </el-avatar>
            <div class="user-basic">
              <div class="user-name">{{ userStore.user?.nickname || userStore.user?.username }}</div>
              <div class="user-meta">
                @{{ userStore.user?.username }}
                <el-tag size="small" style="margin-left: 8px" :type="userStore.user?.is_superuser ? 'danger' : 'success'">
                  {{ userStore.user?.is_superuser ? '管理员' : '普通用户' }}
                </el-tag>
              </div>
            </div>
          </div>
          <el-divider />
          <div class="user-fields">
            <div class="field">
              <span class="label">邮箱</span>
              <span class="value">{{ userStore.user?.email || '未设置' }}</span>
            </div>
            <div class="field">
              <span class="label">账号状态</span>
              <span class="value">
                <el-tag size="small" :type="userStore.user?.is_active ? 'success' : 'danger'">
                  {{ userStore.user?.is_active ? '已激活' : '已禁用' }}
                </el-tag>
              </span>
            </div>
            <div class="field">
              <span class="label">注册时间</span>
              <span class="value">{{ formatTime(userStore.user?.created_at) }}</span>
            </div>
            <div class="field">
              <span class="label">最近更新</span>
              <span class="value">{{ formatTime(userStore.user?.updated_at) }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="16">
        <el-card shadow="never">
          <template #header><div class="card-title">修改个人资料</div></template>
          <el-form :model="profileForm" :rules="profileRules" ref="profileFormRef" label-width="96px">
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="profileForm.nickname" placeholder="选填，用于展示名称" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="profileForm.email" placeholder="选填，用于接收通知" />
            </el-form-item>
            <el-form-item label="头像 URL" prop="avatar">
              <el-input v-model="profileForm.avatar" placeholder="可填写图片 URL" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="handleSaveProfile">保存修改</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" style="margin-top: 20px">
          <template #header><div class="card-title">修改密码</div></template>
          <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="96px">
            <el-form-item label="旧密码" prop="old_password">
              <el-input v-model="passwordForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input v-model="passwordForm.confirm_password" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPwd" @click="handleSavePwd">更新密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { changePasswordApi, updateMeApi } from '@/api/auth'
import dayjs from 'dayjs'

const userStore = useUserStore()

const profileFormRef = ref()
const passwordFormRef = ref()
const saving = ref(false)
const savingPwd = ref(false)

const profileForm = reactive({
  nickname: userStore.user?.nickname || '',
  email: userStore.user?.email || '',
  avatar: userStore.user?.avatar || '',
})

watch(
  () => userStore.user,
  (u) => {
    if (u) {
      profileForm.nickname = u.nickname || ''
      profileForm.email = u.email || ''
      profileForm.avatar = u.avatar || ''
    }
  },
  { immediate: false }
)

const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

const avatarChar = computed(() => {
  const n = userStore.user?.nickname || userStore.user?.username || 'U'
  return n.slice(0, 1).toUpperCase()
})

const profileRules = {
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
}
const passwordRules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_, value, cb) =>
        value !== passwordForm.new_password ? cb(new Error('两次输入的密码不一致')) : cb(),
      trigger: 'blur',
    },
  ],
}

async function handleSaveProfile() {
  if (!profileFormRef.value) return
  await profileFormRef.value.validate()
  saving.value = true
  try {
    const res = await updateMeApi(profileForm)
    await userStore.fetchMe()
    ElMessage.success(res.message || '保存成功')
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function handleSavePwd() {
  if (!passwordFormRef.value) return
  await passwordFormRef.value.validate()
  savingPwd.value = true
  try {
    const res = await changePasswordApi(passwordForm)
    ElMessage.success(res.message || '密码修改成功')
    Object.assign(passwordForm, { old_password: '', new_password: '', confirm_password: '' })
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    savingPwd.value = false
  }
}

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-'
}
</script>

<style lang="scss" scoped>
.profile-page {
  max-width: 1200px;
  margin: 0 auto;
}
.card-title {
  font-weight: 700;
  font-size: 16px;
}
.profile-card {
  .avatar-block {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 4px;
  }
  .user-name {
    font-size: 20px;
    font-weight: 800;
    margin-bottom: 4px;
  }
  .user-meta {
    color: var(--app-text-muted);
    font-size: 13px;
    display: flex;
    align-items: center;
  }
  .user-fields {
    display: flex;
    flex-direction: column;
    gap: 12px;
    .field {
      display: flex;
      justify-content: space-between;
      font-size: 14px;
      .label {
        color: var(--app-text-muted);
      }
    }
  }
}
</style>
