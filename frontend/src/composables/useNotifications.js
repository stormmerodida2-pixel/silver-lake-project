import { ref } from 'vue'

import apiClient from '../api/client'

/**
 * Shared unread-count + list state for the admin notification bell. The count is cheap to poll
 * on its own (see NotificationBell.vue); the list itself is only fetched when the dropdown is
 * actually opened, so a 30s poll doesn't pull a full page of notifications every time.
 */
export function useNotifications() {
  const unreadCount = ref(0)
  const items = ref([])
  const loading = ref(false)

  async function refreshCount() {
    try {
      const { data } = await apiClient.get('/admin/notifications/unread-count/')
      unreadCount.value = data.count
    } catch {
      // Silently do nothing - a missed poll isn't worth surfacing an error over.
    }
  }

  async function loadList() {
    loading.value = true
    try {
      const { data } = await apiClient.get('/admin/notifications/')
      items.value = data.results ?? data
    } catch {
      // Silently do nothing - the bell just stays empty until the next successful load.
    } finally {
      loading.value = false
    }
  }

  async function markRead(notification) {
    if (notification.is_read) return
    notification.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    try {
      await apiClient.post(`/admin/notifications/${notification.id}/mark-read/`)
    } catch {
      // Best-effort - if this fails, it just shows unread again next refresh.
    }
  }

  async function markAllRead() {
    items.value.forEach((n) => { n.is_read = true })
    unreadCount.value = 0
    try {
      await apiClient.post('/admin/notifications/mark-all-read/')
    } catch {
      // Best-effort - if this fails, it just shows unread again next refresh.
    }
  }

  return { unreadCount, items, loading, refreshCount, loadList, markRead, markAllRead }
}
