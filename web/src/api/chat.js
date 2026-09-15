import request from '@/utils/request'

const CHAT_PREFIX = '/chat'

export function listConversationsApi(params) {
  return request.get(`${CHAT_PREFIX}/conversations`, { params })
}

export function createConversationApi(params) {
  return request.post(`${CHAT_PREFIX}/conversations`, params)
}

export function updateConversationApi(id, params) {
  return request.put(`${CHAT_PREFIX}/conversations/${id}`, params)
}

export function deleteConversationApi(id) {
  return request.delete(`${CHAT_PREFIX}/conversations/${id}`)
}

export function getMessagesApi(convId) {
  return request.get(`${CHAT_PREFIX}/conversations/${convId}/messages`)
}

export function buildChatStreamUrl(convId) {
  return `/api/v1${CHAT_PREFIX}/conversations/${convId}/chat`
}
