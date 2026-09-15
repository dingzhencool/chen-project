import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listKbApi,
  createKbApi,
  updateKbApi,
  deleteKbApi,
  getKbApi,
} from '@/api/knowledgeBase'

export const useKbStore = defineStore('knowledgeBase', () => {
  const list = ref([])
  const total = ref(0)
  const current = ref(null)

  async function fetchList(params) {
    const res = await listKbApi(params)
    list.value = res.data.items
    total.value = res.data.total
    return res.data
  }

  async function createOne(params) {
    const res = await createKbApi(params)
    return res.data
  }

  async function updateOne(id, params) {
    const res = await updateKbApi(id, params)
    return res.data
  }

  async function deleteOne(id) {
    await deleteKbApi(id)
    const idx = list.value.findIndex((k) => k.id === id)
    if (idx >= 0) list.value.splice(idx, 1)
    if (current.value?.id === id) current.value = null
  }

  async function fetchDetail(id) {
    const res = await getKbApi(id)
    current.value = res.data
    return res.data
  }

  function setCurrent(kb) {
    current.value = kb
  }

  return {
    list,
    total,
    current,
    fetchList,
    createOne,
    updateOne,
    deleteOne,
    fetchDetail,
    setCurrent,
  }
})
