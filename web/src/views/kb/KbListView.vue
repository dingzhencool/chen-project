<template>
  <div class="kb-list-page">
    <div class="page-toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索知识库名称 / 描述"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
      />
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>新建知识库
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col
        v-for="kb in kbStore.list"
        :key="kb.id"
        :xs="24" :sm="12" :md="8" :lg="6" :xl="6"
      >
        <el-card class="kb-card" shadow="hover" @click="handleOpen(kb)">
          <template #header>
            <div class="kb-card-head">
              <span class="kb-icon">📚</span>
              <span class="kb-name" :title="kb.name">{{ kb.name }}</span>
              <el-dropdown trigger="click" @click.stop @command="(cmd) => handleKbCmd(cmd, kb)">
                <span class="kb-more" @click.stop>⋯</span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
          <div class="kb-desc" :title="kb.description">
            {{ kb.description || '暂无描述' }}
          </div>
          <div class="kb-meta">
            <el-tag size="small" type="info">{{ kb.doc_count || 0 }} 篇文档</el-tag>
            <el-tag size="small" :type="kb.is_active ? 'success' : 'danger'">
              {{ kb.is_active ? '已启用' : '已停用' }}
            </el-tag>
            <span class="kb-time">{{ formatTime(kb.updated_at) }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="pagination">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="kbStore.total"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48]"
        @current-change="fetchList"
        @size-change="fetchList"
      />
    </div>

    <el-dialog v-model="formVisible" :title="editingId ? '编辑知识库' : '新建知识库'" width="520px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="96px">
        <el-form-item label="知识库名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：产品帮助中心" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="知识库用途 / 内容简介" />
        </el-form-item>
        <el-form-item label="检索 TopK" prop="retrieval_top_k">
          <el-input-number v-model="form.retrieval_top_k" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="相似度阈值" prop="similarity_threshold">
          <el-slider v-model="form.similarity_threshold" :min="0" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="分块大小" prop="chunk_size">
          <el-input-number v-model="form.chunk_size" :min="100" :max="2000" :step="50" />
        </el-form-item>
        <el-form-item label="分块重叠" prop="chunk_overlap">
          <el-input-number v-model="form.chunk_overlap" :min="0" :max="500" :step="10" />
        </el-form-item>
        <el-form-item label="是否公开" prop="is_public">
          <el-switch v-model="form.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useKbStore } from '@/stores/knowledgeBase'
import dayjs from 'dayjs'

const kbStore = useKbStore()
const router = useRouter()

const keyword = ref('')
const page = ref(1)
const pageSize = ref(12)

const formVisible = ref(false)
const submitting = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({
  name: '',
  description: '',
  retrieval_top_k: 6,
  similarity_threshold: 0.6,
  chunk_size: 500,
  chunk_overlap: 50,
  is_public: false,
})
const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

onMounted(() => fetchList())

async function fetchList() {
  await kbStore.fetchList({
    page: page.value,
    page_size: pageSize.value,
    keyword: keyword.value || undefined,
  })
}

function handleSearch() {
  page.value = 1
  fetchList()
}

function handleCreate() {
  editingId.value = null
  Object.assign(form, {
    name: '',
    description: '',
    retrieval_top_k: 6,
    similarity_threshold: 0.6,
    chunk_size: 500,
    chunk_overlap: 50,
    is_public: false,
  })
  formVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate()
  submitting.value = true
  try {
    if (editingId.value) {
      await kbStore.updateOne(editingId.value, form)
      ElMessage.success('更新成功')
    } else {
      await kbStore.createOne(form)
      ElMessage.success('创建成功')
    }
    formVisible.value = false
    fetchList()
  } catch (e) {
    if (e?.message) ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

function handleOpen(kb) {
  router.push(`/kb/${kb.id}`)
}

async function handleKbCmd(cmd, kb) {
  if (cmd === 'edit') {
    editingId.value = kb.id
    Object.assign(form, {
      name: kb.name,
      description: kb.description,
      retrieval_top_k: kb.retrieval_top_k,
      similarity_threshold: Number(kb.similarity_threshold || 0.6),
      chunk_size: kb.chunk_size,
      chunk_overlap: kb.chunk_overlap,
      is_public: kb.is_public,
    })
    formVisible.value = true
  }
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确认删除知识库「${kb.name}」？相关文档也会被移除。`, '提示', { type: 'warning' })
      await kbStore.deleteOne(kb.id)
      ElMessage.success('已删除')
      fetchList()
    } catch (e) { /* cancel */ }
  }
}

function formatTime(t) {
  return dayjs(t).format('YYYY-MM-DD HH:mm')
}
</script>

<style lang="scss" scoped>
.kb-list-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.page-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  .search-input {
    flex: 1;
    max-width: 480px;
  }
}
.kb-card {
  height: 100%;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  &:hover {
    transform: translateY(-2px);
  }
  .kb-card-head {
    display: flex;
    align-items: center;
    gap: 10px;
    .kb-icon {
      font-size: 20px;
    }
    .kb-name {
      flex: 1;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-weight: 700;
    }
    .kb-more {
      padding: 2px 8px;
      border-radius: 4px;
      &:hover {
        background: var(--app-bg-color);
      }
    }
  }
  .kb-desc {
    color: var(--app-text-muted);
    font-size: 13px;
    line-height: 1.6;
    height: 62px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
  }
  .kb-meta {
    margin-top: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    .kb-time {
      margin-left: auto;
      font-size: 12px;
      color: var(--app-text-muted);
    }
  }
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
