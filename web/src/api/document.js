import request from '@/utils/request'

const DOC_PREFIX = '/documents'

export function uploadDocumentApi(kbId, file, onProgress) {
  const formData = new FormData()
  formData.append('kb_id', kbId)
  formData.append('file', file)
  return request.post(`${DOC_PREFIX}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
    // 大文档入库耗时与分块数正相关（138 块约 55 秒，568 块约 3~4 分钟），
    // 不能走全局 30s 超时，否则服务端其实处理成功了，前端却误报 timeout
    timeout: 300000,
  })
}

export function listDocumentsApi(params) {
  return request.get(DOC_PREFIX, { params })
}

export function deleteDocumentApi(id) {
  return request.delete(`${DOC_PREFIX}/${id}`)
}

// 引用验真：取某条引用对应分块的原文（含前后相邻块、PDF 页码）
export function getChunkContextApi(docId, chunkIndex) {
  return request.get(`${DOC_PREFIX}/${docId}/chunks/${chunkIndex}`)
}

// 引用验真：带鉴权拉取原文件二进制（PDF/图片用于浏览器内联预览），返回 Blob
export function fetchDocumentFileApi(docId) {
  return request.get(`${DOC_PREFIX}/${docId}/file`, { responseType: 'blob' })
}
