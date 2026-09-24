import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listConversationsApi,
  createConversationApi,
  updateConversationApi,
  deleteConversationApi,
  getMessagesApi,
} from '@/api/chat'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const total = ref(0)
  const currentConversation = ref(null)
  const messages = ref([])

  async function fetchList(params) {
    const res = await listConversationsApi(params)
    conversations.value = res.data.items
    total.value = res.data.total
    return res.data
  }

  function reset() {
    conversations.value = []
    total.value = 0
    currentConversation.value = null
    messages.value = []
  }

  async function createOne(params) {
    const res = await createConversationApi(params)
    const item = res.data
    conversations.value.unshift(item)
    currentConversation.value = item
    messages.value = []
    return item
  }

  async function updateOne(id, params) {
    const res = await updateConversationApi(id, params)
    const item = res.data
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx >= 0) conversations.value.splice(idx, 1, item)
    if (currentConversation.value?.id === id) currentConversation.value = item
    return item
  }

  async function deleteOne(id) {
    await deleteConversationApi(id)
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx >= 0) conversations.value.splice(idx, 1)
    if (currentConversation.value?.id === id) {
      currentConversation.value = null
      messages.value = []
    }
  }

  async function selectConversation(conv) {
    currentConversation.value = conv
    if (conv) {
      const res = await getMessagesApi(conv.id)
      messages.value = res.data || []
    } else {
      messages.value = []
    }
  }

  function appendUserMessage(msg) {
    messages.value.push(msg)
  }

  function appendAssistantDelta(delta) {
    const lastIdx = messages.value.length - 1
    if (lastIdx < 0 || messages.value[lastIdx].role !== 'assistant') {
      messages.value.push({ role: 'assistant', content: delta, _appending: true })
    } else {
      messages.value[lastIdx].content += delta
    }
  }

  function markAssistantDone(finalMsg) {
    const lastIdx = messages.value.length - 1
    if (lastIdx >= 0 && messages.value[lastIdx]._appending) {
      messages.value.splice(lastIdx, 1, finalMsg)
    } else {
      messages.value.push(finalMsg)
    }
  }

  return {
    conversations,
    total,
    currentConversation,
    messages,
    fetchList,
    reset,
    createOne,
    updateOne,
    deleteOne,
    selectConversation,
    appendUserMessage,
    appendAssistantDelta,
    markAssistantDone,
  }
})
