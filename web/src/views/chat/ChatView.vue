<template>
  <div class="chat-page">
    <aside class="conv-sidebar">
      <el-button type="primary" class="new-chat-btn" @click="handleNewChat">
        <el-icon><Plus /></el-icon>
        <span>新建对话</span>
      </el-button>
      <div class="conv-list" v-loading="loadingList">
        <div
          v-for="conv in chatStore.conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ 'conv-item--active': chatStore.currentConversation?.id === conv.id }"
          @click="handleSelect(conv)"
        >
          <span class="conv-icon">💬</span>
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <el-dropdown trigger="click" @click.stop @command="(cmd) => handleConvCmd(cmd, conv)">
            <span class="conv-more" @click.stop>⋯</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-empty v-if="!loadingList && chatStore.conversations.length === 0" description="暂无对话，点击上方按钮开始" />
      </div>
    </aside>

    <section class="chat-main">
      <div v-if="!chatStore.currentConversation" class="chat-empty">
        <div class="empty-logo">🤖</div>
        <h2>选择或创建一个对话开始</h2>
        <p>您可以关联知识库，让 AI 基于您的文档精准回答问题</p>
        <el-button type="primary" size="large" @click="handleNewChat">立即开始</el-button>
      </div>

      <template v-else>
        <header class="chat-header">
          <el-select
            v-model="currentKbId"
            placeholder="关联知识库（选填）"
            clearable
            filterable
            class="kb-select"
            @change="handleKbChange"
          >
            <el-option v-for="k in kbStore.list" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </header>

        <div class="messages" ref="messagesRef" v-loading="loadingMsg">
          <div v-if="chatStore.messages.length === 0" class="chat-welcome">
            <el-result icon="info" title="准备就绪" sub-title="输入问题开始与 AI 对话，支持 SSE 流式输出">
              <template #extra>
                <el-input v-model="quickInput" size="large" placeholder="例如：这份文档介绍了什么？">
                  <template #append>
                    <el-button type="primary" @click="handleQuickSend">发送</el-button>
                  </template>
                </el-input>
              </template>
            </el-result>
          </div>
          <div
            v-for="(msg, idx) in chatStore.messages"
            :key="msg.id || ('tmp-' + idx)"
            class="msg-row"
            :class="msg.role === 'user' ? 'msg-row--user' : 'msg-row--assistant'"
          >
            <div class="msg-avatar">{{ msg.role === 'user' ? '🧑' : '🤖' }}</div>
            <div class="msg-bubble">
              <div class="msg-content">{{ plainText(msg.content) }}</div>
              <div v-if="msg.role === 'assistant' && cleanSources(msg.sources).length > 0" class="msg-sources">
                <div class="source-title">📎 引用来源（点击可查看原文验真）</div>
                <div
                  v-for="(s, i) in cleanSources(msg.sources)"
                  :key="`${s.document_id}_${s.chunk_index}_${i}`"
                  class="source-item source-item--link"
                  title="点击查看该引用在原文件中的原文片段"
                  @click="openVerify(s)"
                >
                  <span class="source-link">
                    [{{ i + 1 }}] {{ s.document_name ? s.document_name.replace(/\s+/g, ' ').trim() : ('来源 ' + (i + 1)) }}
                  </span>
                  <span class="score">相似度：{{ (s.score || 0).toFixed(3) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <footer class="chat-input">
          <el-input
            v-model="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 5 }"
            placeholder="输入您的问题，Enter 发送，Shift + Enter 换行"
            :disabled="sending"
            resize="none"
            @keydown.enter.exact.prevent="handleSend"
          />
          <el-button type="primary" :loading="sending" class="send-btn" @click="handleSend">发送</el-button>
        </footer>
      </template>
    </section>

    <!-- 引用验真抽屉：展示命中块原文 + 前后文 + PDF 页码，并可打开原文件 -->
    <el-drawer
      v-model="verifyVisible"
      size="46%"
      :with-header="false"
      direction="rtl"
      class="verify-drawer"
    >
      <div v-loading="verifyLoading" class="verify-panel">
        <template v-if="verifyData">
          <div class="verify-head">
            <div class="verify-title">🔎 引用原文验真</div>
            <button class="verify-close" @click="verifyVisible = false">✕</button>
          </div>

          <div class="verify-meta">
            <div class="verify-file">📄 {{ verifyData.document_name }}</div>
            <div class="verify-tags">
              <el-tag size="small" type="info">分块 {{ verifyData.chunk_index }} / {{ verifyData.chunk_total - 1 }}</el-tag>
              <el-tag v-if="verifyData.page_start" size="small" type="warning">
                第 {{ verifyData.page_start }}{{ verifyData.page_end && verifyData.page_end !== verifyData.page_start ? '~' + verifyData.page_end : '' }} 页
              </el-tag>
              <el-tag v-if="verifyScore != null" size="small" type="success">相似度 {{ Number(verifyScore).toFixed(3) }}</el-tag>
              <el-tag size="small">{{ (verifyData.file_type || '').toUpperCase() }}</el-tag>
            </div>
          </div>

          <!-- 图片类来源：直接展示原图 -->
          <div v-if="verifyImageUrl" class="verify-image-wrap">
            <img :src="verifyImageUrl" alt="来源图片" class="verify-image" />
          </div>

          <div class="verify-tip">
            下方为 AI 回答实际依据的原文片段（命中块高亮），可逐句核对回答是否与资料一致：
          </div>

          <div v-if="verifyData.prev" class="verify-context verify-context--around">
            <div class="ctx-label">上文</div>
            <div class="ctx-text">{{ formatChunkText(verifyData.prev) }}</div>
          </div>

          <div class="verify-context verify-context--hit">
            <div class="ctx-label">🎯 AI 引用的原文片段</div>
            <div class="ctx-text">{{ formatChunkText(verifyData.current) }}</div>
          </div>

          <div v-if="verifyData.next" class="verify-context verify-context--around">
            <div class="ctx-label">下文</div>
            <div class="ctx-text">{{ formatChunkText(verifyData.next) }}</div>
          </div>

          <div class="verify-actions">
            <el-button
              type="primary"
              :loading="fileOpening"
              @click="openOriginalFile"
            >
              {{ openFileLabel }}
            </el-button>
            <span class="verify-action-hint">
              {{ verifyData.file_type === 'pdf' && verifyData.page_start ? `新窗口打开 PDF 并定位到第 ${verifyData.page_start} 页` : '在新窗口打开原文件（DOCX 会下载后用 Word 打开）' }}
            </span>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { useKbStore } from '@/stores/knowledgeBase'
import { updateConversationApi } from '@/api/chat'
import { buildChatStreamUrl } from '@/api/chat'
import { getChunkContextApi, fetchDocumentFileApi } from '@/api/document'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const chatStore = useChatStore()
const kbStore = useKbStore()

const loadingList = ref(false)
const loadingMsg = ref(false)
const sending = ref(false)
const messagesRef = ref(null)
const inputText = ref('')
const quickInput = ref('')
const currentKbId = ref(null)
const currentKbName = ref('')

/**
 * 纯文本展示兜底：系统按纯文本渲染（不走 Markdown），模型偶发输出的 **加粗** / *斜体*
 * 星号会原样显示。这里在渲染前去掉强调符号，保留文字本身；不动原始数据，流式中途
 * 落单的 ** 也先清掉，闭合后成对内容自然还原，不会闪星号。
 */
function plainText(text) {
  if (!text) return ''
  return String(text)
    .replace(/\*\*([\s\S]+?)\*\*/g, '$1') // 成对 **加粗** → 文字
    .replace(/\*\*/g, '')                 // 流式中途/落单的 **
    .replace(/\*([^*\n]+?)\*/g, '$1')     // 成对 *斜体* → 文字
}

/* ==================== 引用原文验真 ==================== */
const IMAGE_TYPES = ['png', 'jpg', 'jpeg', 'webp', 'bmp']
const verifyVisible = ref(false)
const verifyLoading = ref(false)
const verifyData = ref(null)
const verifyScore = ref(null)
const verifyImageUrl = ref('')
const fileOpening = ref(false)
let verifyBlobUrl = ''

function revokeVerifyBlob() {
  if (verifyBlobUrl) {
    URL.revokeObjectURL(verifyBlobUrl)
    verifyBlobUrl = ''
  }
}

// chunk 原文里 PDF 解析注入的 --- Page N --- 锚点，转成可读的页码徽标文本
function formatChunkText(text) {
  if (!text) return ''
  return plainText(String(text))
    .replace(/---\s*Page\s+(\d+)\s*---/g, '〔第 $1 页〕')
    .replace(/^\s+/, '')
}

async function openVerify(source) {
  const docId = source.document_id
  const chunkIndex = source.chunk_index
  if (!docId && docId !== 0) {
    ElMessage.warning('该引用缺少文档标识，无法定位原文')
    return
  }
  revokeVerifyBlob()
  verifyImageUrl.value = ''
  verifyData.value = null
  verifyScore.value = source.score ?? null
  verifyVisible.value = true
  verifyLoading.value = true
  try {
    const res = await getChunkContextApi(docId, chunkIndex ?? 0)
    verifyData.value = res.data
    // 图片类来源顺手拉取原图，直接在抽屉里展示
    if (IMAGE_TYPES.includes((res.data.file_type || '').toLowerCase())) {
      const blob = await fetchDocumentFileApi(docId)
      revokeVerifyBlob()
      verifyBlobUrl = URL.createObjectURL(blob)
      verifyImageUrl.value = verifyBlobUrl
    }
  } catch (e) {
    // 拦截器已统一弹错误提示；失败时关掉 loading，抽屉保持空态
    verifyVisible.value = false
  } finally {
    verifyLoading.value = false
  }
}

const openFileLabel = computed(() => {
  if (!verifyData.value) return '📂 打开原文件'
  const t = (verifyData.value.file_type || '').toLowerCase()
  if (t === 'pdf' && verifyData.value.page_start) return `📖 打开 PDF（定位到第 ${verifyData.value.page_start} 页）`
  if (IMAGE_TYPES.includes(t)) return '🖼️ 新窗口查看原图'
  if (t === 'docx' || t === 'doc') return '⬇️ 下载原文件（用 Word 打开）'
  return '📂 打开原文件'
})

async function openOriginalFile() {
  if (!verifyData.value) return
  const d = verifyData.value
  fileOpening.value = true
  try {
    // 图片已在抽屉里加载过 blob，优先复用；其余类型重新拉取
    let url = verifyBlobUrl
    if (!url) {
      const blob = await fetchDocumentFileApi(d.document_id)
      revokeVerifyBlob()
      verifyBlobUrl = URL.createObjectURL(blob)
      url = verifyBlobUrl
    }
    // PDF 用 #page=N 让浏览器内置阅读器直接跳到引用所在页；图片/文本无需锚点
    const anchor = d.file_type === 'pdf' && d.page_start ? `#page=${d.page_start}` : ''
    const win = window.open(url + anchor, '_blank')
    if (!win) ElMessage.warning('浏览器拦截了新窗口，请允许弹窗后重试')
  } catch (e) {
    // 错误提示已由拦截器处理
  } finally {
    fileOpening.value = false
  }
}

watch(verifyVisible, (v) => {
  if (!v) {
    // 抽屉关闭后延迟回收 blob，避免仍在加载的窗口失效
    setTimeout(revokeVerifyBlob, 30000)
  }
})

/**
 * 引用来源清洗（前端最后一道过滤保险，兜底历史脏数据或后端异常）：
 * 1) 兼容 sources 是 JSON 字符串的旧数据（手动 parse）；
 * 2) 移除 score <= 0 的噪声/占位；
 * 3) 对 (document_id, chunk_index) 去重，保留最高分；
 * 4) 按 score 降序排序并重新编号；
 * 5) 返回 [] 时 UI 整个「引用来源」块自动隐藏。
 */
function cleanSources(sources) {
  if (!sources) return []
  // 兼容历史脏数据/契约断裂：sources 可能是 JSON 字符串
  let arr = sources
  if (typeof arr === 'string') {
    try { arr = JSON.parse(arr) } catch { arr = [] }
  }
  if (!Array.isArray(arr) || arr.length === 0) return []
  const dedup = new Map()
  for (const s of arr) {
    if (!s || typeof s !== 'object') continue
    const sc = Number(s.score ?? 0) || 0
    if (sc <= 0) continue
    const key = `${s.document_id ?? 0}_${s.chunk_index ?? 0}`
    const prev = dedup.get(key)
    if (!prev || sc > (Number(prev.score ?? 0) || 0)) {
      dedup.set(key, { ...s, score: sc })
    }
  }
  return Array.from(dedup.values()).sort((a, b) => (b.score || 0) - (a.score || 0))
}

onMounted(async () => {
  loadingList.value = true
  try {
    await Promise.all([
      chatStore.fetchList({ page: 1, page_size: 50 }),
      kbStore.fetchList({ page: 1, page_size: 100 }),
    ])
    if (chatStore.conversations.length > 0) {
      currentKbId.value = chatStore.conversations[0].kb_id
      await chatStore.selectConversation(chatStore.conversations[0])
    }
  } finally {
    loadingList.value = false
  }
})

watch(
  () => chatStore.messages,
  () => nextTick(scrollBottom),
  { deep: true }
)

function scrollBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

async function handleNewChat() {
  const kbName = currentKbId.value
    ? kbStore.list.find((k) => k.id === currentKbId.value)?.name || ''
    : ''
  const title = kbName ? `${kbName} 对话` : '新对话'
  await chatStore.createOne({ kb_id: currentKbId.value || null, title, mode: 'chat' })
  inputText.value = ''
}

async function handleSelect(conv) {
  loadingMsg.value = true
  try {
    currentKbId.value = conv.kb_id
    await chatStore.selectConversation(conv)
  } finally {
    loadingMsg.value = false
  }
}

async function handleConvCmd(cmd, conv) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('请输入新的标题', '重命名对话', {
        inputValue: conv.title,
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      await chatStore.updateOne(conv.id, { title: value || conv.title })
      ElMessage.success('已更新')
    } catch (e) { /* cancel */ }
  }
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('确认删除该对话？', '提示', { type: 'warning' })
      await chatStore.deleteOne(conv.id)
      ElMessage.success('已删除')
    } catch (e) { /* cancel */ }
  }
}

async function handleKbChange(val) {
  if (!chatStore.currentConversation) return
  const newKb = val === undefined || val === '' ? null : val
  const oldKb = chatStore.currentConversation.kb_id
  if (newKb === oldKb) return
  try {
    const res = await updateConversationApi(chatStore.currentConversation.id, { kb_id: newKb })
    // 以服务端返回的 data.kb_id 为准（拦截器已抛 code!=0，这里必然 code=0）
    if (res?.data && typeof res.data.kb_id !== 'undefined') {
      chatStore.currentConversation.kb_id = res.data.kb_id
      currentKbId.value = res.data.kb_id
    } else {
      chatStore.currentConversation.kb_id = newKb
      currentKbId.value = newKb
    }
    ElMessage.success(newKb ? '已关联知识库' : '已取消关联')
  } catch (e) {
    // 拦截器已提示具体错误，这里严格回滚 UI 状态
    currentKbId.value = oldKb
    chatStore.currentConversation.kb_id = oldKb
  }
}

async function handleSend() {
  const content = (inputText.value || '').trim()
  if (!content) return
  if (!chatStore.currentConversation) {
    await handleNewChat()
  }
  const conv = chatStore.currentConversation
  if (!conv) return

  inputText.value = ''
  sending.value = true
  chatStore.appendUserMessage({ role: 'user', content, created_at: new Date().toISOString() })

  try {
    const url = buildChatStreamUrl(conv.id)
    const token = localStorage.getItem('token')
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({
        content,
        // 消息级 override_kb_id：优先使用顶部下拉当前值
        // 即使 conv.kb_id 还没在 DB 里更新完，检索立即生效（双保险第一重）
        override_kb_id: currentKbId.value === undefined || currentKbId.value === ''
          ? null
          : currentKbId.value,
      }),
    })
    if (!resp.ok || !resp.body) {
      throw new Error('流式请求失败')
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let finalMessage = null
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const raw of lines) {
        const line = raw.trim()
        if (!line || !line.startsWith('data:')) continue
        const jsonStr = line.slice(5).trim()
        if (!jsonStr) continue
        try {
          const payload = JSON.parse(jsonStr)
            if (payload.type === 'delta') {
              chatStore.appendAssistantDelta(payload.delta || '')
            } else if (payload.type === 'error') {
              // 后端检索/生成失败（如向量模型额度耗尽）：弹可读原因，同时写入气泡便于回看
              ElMessage.error({
                message: payload.message || '生成失败',
                duration: 8000,
                showClose: true,
              })
              chatStore.appendAssistantDelta('\n\n[服务提示] ' + (payload.message || '生成失败'))
            } else if (payload.type === 'done') {
              finalMessage = payload.message
              // 双保险：以 payload.sources 为准覆盖 message.sources，兼容后端旧版本契约断裂时的字符串 sources
              if (Array.isArray(payload.sources)) {
                finalMessage.sources = payload.sources
              }
            }
        } catch (e) { /* ignore */ }
      }
    }
    if (finalMessage) {
      chatStore.markAssistantDone(finalMessage)
    }
  } catch (e) {
    ElMessage.error(e.message || '对话失败')
    chatStore.appendAssistantDelta('[系统错误] ' + (e.message || '对话失败'))
  } finally {
    sending.value = false
    nextTick(scrollBottom)
  }
}

function handleQuickSend() {
  if (!quickInput.value.trim()) return
  inputText.value = quickInput.value
  quickInput.value = ''
  handleSend()
}
</script>

<style lang="scss" scoped>
.chat-page {
  display: flex;
  height: 100%;
  gap: 16px;
}
.conv-sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--app-card-bg);
  border-radius: 12px;
  border: 1px solid var(--app-border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  .new-chat-btn {
    margin: 16px;
    width: calc(100% - 32px);
    justify-content: center;
  }
  .conv-list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 0 12px 12px;
  }
  .conv-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s;
    &:hover {
      background: var(--app-bg-color);
    }
    &--active {
      background: var(--app-primary-light);
      color: var(--app-primary);
      font-weight: 600;
    }
    .conv-title {
      flex: 1;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 14px;
    }
    .conv-more {
      opacity: 0;
      padding: 2px 6px;
      border-radius: 4px;
      transition: all 0.2s;
      &:hover {
        background: rgba(0, 0, 0, 0.05);
      }
    }
    &:hover .conv-more {
      opacity: 1;
    }
  }
}
.chat-main {
  flex: 1;
  min-width: 0;
  background: var(--app-card-bg);
  border-radius: 12px;
  border: 1px solid var(--app-border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px;
  .empty-logo {
    font-size: 80px;
    line-height: 1;
    margin-bottom: 16px;
  }
  h2 {
    font-size: 24px;
    margin: 0 0 8px;
  }
  p {
    color: var(--app-text-muted);
    margin: 0 0 24px;
  }
}
.chat-header {
  height: 56px;
  border-bottom: 1px solid var(--app-border-color);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  .kb-select {
    width: 280px;
  }
}
.messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.chat-welcome {
  margin: auto 0;
}
.msg-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  max-width: 85%;
  &--user {
    align-self: flex-end;
    flex-direction: row-reverse;
    .msg-bubble {
      background: var(--app-chat-user-bg);
      border-radius: 16px 16px 4px 16px;
    }
  }
  &--assistant {
    align-self: flex-start;
    .msg-bubble {
      background: var(--app-chat-assistant-bg);
      border: 1px solid var(--app-border-color);
      border-radius: 16px 16px 16px 4px;
    }
  }
  .msg-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--app-primary-light);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
  }
  .msg-bubble {
    padding: 12px 16px;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 14px;
    line-height: 1.7;
  }
  .msg-content {
    white-space: pre-wrap;
  }
  .msg-sources {
    margin-top: 10px;
    padding: 10px 12px;
    background: rgba(0, 0, 0, 0.02);
    border-radius: 8px;
    border: 1px dashed var(--app-border-color);
    .source-title {
      font-size: 12px;
      color: var(--app-text-muted);
      margin-bottom: 4px;
      font-weight: 600;
    }
    .source-item {
      font-size: 12px;
      padding: 2px 0;
      color: var(--app-text-muted);
      .score {
        margin-left: 8px;
        color: var(--app-primary);
      }
    }
    .source-item--link {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 4px 8px;
      margin: 2px 0;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.15s;
      .source-link {
        color: #4f46e5;
      }
      &:hover {
        background: rgba(79, 70, 229, 0.08);
        .source-link { text-decoration: underline; }
      }
    }
  }
}
.chat-input {
  padding: 12px 20px 20px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  border-top: 1px solid var(--app-border-color);
  .send-btn {
    height: 40px;
    min-width: 88px;
  }
}

/* ==================== 引用验真抽屉 ==================== */
.verify-panel {
  padding: 20px 22px 32px;
}
.verify-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.verify-title {
  font-size: 17px;
  font-weight: 700;
  color: #1f2937;
}
.verify-close {
  border: none;
  background: transparent;
  font-size: 16px;
  color: #9ca3af;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  &:hover { background: #f3f4f6; color: #374151; }
}
.verify-meta {
  margin-bottom: 14px;
}
.verify-file {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
  word-break: break-all;
}
.verify-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.verify-image-wrap {
  margin: 12px 0;
  text-align: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  background: #fafafa;
}
.verify-image {
  max-width: 100%;
  border-radius: 4px;
}
.verify-tip {
  font-size: 12px;
  color: #6b7280;
  margin: 12px 0 10px;
  line-height: 1.6;
}
.verify-context {
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  line-height: 1.85;
  font-size: 13.5px;
  white-space: pre-wrap;
  word-break: break-word;
}
.verify-context--around {
  background: #f9fafb;
  border: 1px solid #f0f0f0;
  color: #6b7280;
  .ctx-label {
    font-size: 11px;
    color: #9ca3af;
    margin-bottom: 4px;
    font-weight: 600;
  }
}
.verify-context--hit {
  background: #eef2ff;
  border: 1.5px solid #6366f1;
  color: #1e1b4b;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
  .ctx-label {
    font-size: 12px;
    color: #4f46e5;
    margin-bottom: 6px;
    font-weight: 700;
  }
}
.verify-actions {
  margin-top: 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.verify-action-hint {
  font-size: 12px;
  color: #9ca3af;
}
</style>
