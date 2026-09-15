<template>
  <div class="kb-detail" v-loading="loading">
    <div class="detail-header" v-if="kbStore.current">
      <div class="info-block">
        <el-button link type="primary" @click="$router.back()">← 返回列表</el-button>
        <h2 class="kb-title">{{ kbStore.current.name }}</h2>
        <p class="kb-desc">{{ kbStore.current.description || '暂无描述' }}</p>
        <div class="kb-stats">
          <el-tag>{{ kbStore.current.doc_count || 0 }} 篇文档</el-tag>
          <el-tag type="info">TopK: {{ kbStore.current.retrieval_top_k }}</el-tag>
          <el-tag type="info">相似度: {{ Number(kbStore.current.similarity_threshold || 0).toFixed(2) }}</el-tag>
          <el-tag type="info">Chunk: {{ kbStore.current.chunk_size }} / {{ kbStore.current.chunk_overlap }}</el-tag>
        </div>
      </div>
      <div class="action-block">
        <el-upload
          :show-file-list="false"
          :http-request="handleUpload"
          accept=".pdf,.docx,.doc,.txt,.md,.markdown,.png,.jpg,.jpeg,.webp,.bmp"
          multiple
        >
          <el-button type="primary" size="large">📤 上传文档 / 图片</el-button>
        </el-upload>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="table-header">
          <span>文档列表（共 {{ total }} 条）</span>
          <el-input v-model="filterText" placeholder="按文件名搜索" size="small" clearable style="width: 240px" />
        </div>
      </template>
      <el-table :data="filteredDocs" v-loading="loadingDoc" stripe>
        <el-table-column prop="filename" label="文件名" min-width="240">
          <template #default="{ row }">
            <div class="doc-name-row">
              <span class="doc-icon">{{ fileIcon(row.file_type) }}</span>
              <span>{{ row.filename }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="file_type" label="格式" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ (row.file_type || '').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块数" width="80" align="center" />
        <el-table-column label="状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误信息" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.status === 'failed'" class="status-fail">{{ row.error_msg }}</span>
            <span v-else class="status-ok">-</span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="pagination">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        @current-change="fetchDocs"
        @size-change="fetchDocs"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useKbStore } from '@/stores/knowledgeBase'
import { deleteDocumentApi, listDocumentsApi, uploadDocumentApi } from '@/api/document'
import dayjs from 'dayjs'

const route = useRoute()
const kbStore = useKbStore()
const kbId = Number(route.params.id)

const loading = ref(false)
const loadingDoc = ref(false)
const uploadings = ref(0)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const docs = ref([])
const filterText = ref('')

const filteredDocs = computed(() => {
  const kw = (filterText.value || '').trim().toLowerCase()
  if (!kw) return docs.value
  return docs.value.filter((d) => d.filename.toLowerCase().includes(kw))
})

onMounted(async () => {
  loading.value = true
  try {
    await kbStore.fetchDetail(kbId)
    await fetchDocs()
  } finally {
    loading.value = false
  }
})

async function fetchDocs() {
  loadingDoc.value = true
  try {
    const res = await listDocumentsApi({
      kb_id: kbId,
      page: page.value,
      page_size: pageSize.value,
    })
    docs.value = res.data.items
    total.value = res.data.total
  } finally {
    loadingDoc.value = false
  }
}

async function handleUpload(req) {
  uploadings.value++
  try {
    const res = await uploadDocumentApi(kbId, req.file)
    const doc = res.data || {}
    if (doc.status === 'failed') {
      // 向量化失败（典型：向量模型不可用/额度耗尽）：明确弹错误原因，不假装成功
      ElMessage.error({
        message: `「${doc.filename}」向量化失败：${doc.error_msg || res.message || '未知错误'}`,
        duration: 8000,
        showClose: true,
      })
      req.onSuccess(doc)
    } else {
      ElMessage.success(`上传并向量化成功：${doc.filename}`)
      req.onSuccess(doc)
    }
    fetchDocs()
  } catch (e) {
    req.onError(e)
  } finally {
    uploadings.value--
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.filename}」？`, '提示', { type: 'warning' })
    await deleteDocumentApi(row.id)
    ElMessage.success('已删除')
    fetchDocs()
  } catch (e) { /* cancel */ }
}

function statusText(s) {
  return { pending: '待处理', processing: '处理中', ready: '就绪', failed: '失败' }[s] || s
}
function statusType(s) {
  return { pending: 'info', processing: 'warning', ready: 'success', failed: 'danger' }[s] || 'info'
}
function fileIcon(t) {
  return {
    pdf: '📕', doc: '📘', docx: '📘', txt: '📄', md: '📋', markdown: '📋',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', webp: '🖼️', bmp: '🖼️',
  }[t] || '📎'
}
function formatSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = Number(bytes) || 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n < 10 && i > 0 ? 2 : 1)} ${units[i]}`
}
function formatTime(t) {
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss')
}
</script>

<style lang="scss" scoped>
.kb-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-border-color);
  border-radius: 12px;
  .kb-title {
    margin: 8px 0 6px;
    font-size: 22px;
    font-weight: 800;
  }
  .kb-desc {
    margin: 0 0 14px;
    color: var(--app-text-muted);
  }
  .kb-stats {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
}
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
}
.doc-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  .doc-icon {
    font-size: 18px;
  }
}
.status-fail {
  color: #ef4444;
  font-size: 12px;
}
.status-ok {
  color: var(--app-text-muted);
}
.pagination {
  display: flex;
  justify-content: flex-end;
}
</style>
