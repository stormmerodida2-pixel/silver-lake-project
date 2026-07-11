import { ref, watch } from 'vue'

import apiClient from '../api/client'

/**
 * `filters`, if passed, is a `reactive()` object of query params (search text, status, etc.) -
 * changing it debounces a fresh `load()` automatically, on top of the initial `onMounted(load)`
 * every view already does. Omit it for a view with no search/filter UI - behaves exactly as
 * before.
 */
export function useAdminList(endpoint, filters = null) {
  const items = ref([])
  const nextUrl = ref(null)
  const loading = ref(true)
  const loadingMore = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const { data } = await apiClient.get(endpoint, filters ? { params: filters } : undefined)
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

  if (filters) {
    // A reactive object passed as watch source is deep-watched automatically - no explicit
    // { deep: true } needed. Debounced so typing in a search box doesn't fire a request per
    // keystroke.
    let debounceTimer = null
    watch(filters, () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(load, 300)
    })
  }

  return { items, nextUrl, loading, loadingMore, error, load, loadMore }
}
