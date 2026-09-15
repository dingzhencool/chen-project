import request from '@/utils/request'

const AUTH_PREFIX = '/auth'

export function registerApi(params) {
  return request.post(`${AUTH_PREFIX}/register`, params)
}

export function loginApi(params) {
  return request.post(`${AUTH_PREFIX}/login`, params)
}

export function getMeApi() {
  return request.get(`${AUTH_PREFIX}/me`)
}

export function updateMeApi(params) {
  return request.put(`${AUTH_PREFIX}/me`, params)
}

export function changePasswordApi(params) {
  return request.put(`${AUTH_PREFIX}/me/password`, params)
}
