import { ref } from 'vue'

import apiClient from '../api/client'

export function useAdminList(endpoint) {
  const items = ref([])
  const nextUrl = ref(null)
  const loading = ref(true)
  const loadingMore = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const { data } = await apiClient.get(endpoint)
      items.value = data.results ?? data
      nextUrl.value = data.next ?? null
    } catch (err) {
      error.value = 'Could not load data.'
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!nextUrl.value) return
    loadingMore.value = true
    try {
      const { data } = await apiClient.get(nextUrl.value)
      items.value = items.value.concat(data.results ?? [])
      nextUrl.value = data.next ?? null
    } catch (err) {
      error.value = 'Could not load more.'
    } finally {
      loadingMore.value = false
    }
  }

  return { items, nextUrl, loading, loadingMore, error, load, loadMore }
}
