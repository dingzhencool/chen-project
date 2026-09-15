import request from '@/utils/request'

const KB_PREFIX = '/knowledge-bases'

export function listKbApi(params) {
  return request.get(KB_PREFIX, { params })
}

export function createKbApi(params) {
  return request.post(KB_PREFIX, params)
}

export function getKbApi(id) {
  return request.get(`${KB_PREFIX}/${id}`)
}

export function updateKbApi(id, params) {
  return request.put(`${KB_PREFIX}/${id}`, params)
}

export function deleteKbApi(id) {
  return request.delete(`${KB_PREFIX}/${id}`)
}
