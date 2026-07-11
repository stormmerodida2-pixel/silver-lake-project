import { ref } from 'vue'

import apiClient from '../api/client'

/**
 * Shared unread-count + list state for a notification bell - used by both the admin dashboard
 * ('/admin/notifications') and the driver portal ('/driver/notifications'), which are separate
 * scoped feeds on the backend (see notifications.views.NotificationViewSet /
 * DriverNotificationViewSet). The count is cheap to poll on its own (see NotificationBell.vue);
 * the list itself is only fetched when the dropdown is actually opened, so a 30s poll doesn't
 * pull a full page of notifications every time.
 */
export function useNotifications(basePath) {
  const unreadCount = ref(0)
  const items = ref([])
  const loading = ref(false)

  async function refreshCount() {
    try {
      const { data } = await apiClient.get(`${basePath}/unread-count/`)
      unreadCount.value = data.count
    } catch {
      // Silently do nothing - a missed poll isn't worth surfacing an error over.
    }
  }

  async function loadList() {
    loading.value = true
    try {
      const { data } = await apiClient.get(`${basePath}/`)
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
      await apiClient.post(`${basePath}/${notification.id}/mark-read/`)
    } catch {
      // Best-effort - if this fails, it just shows unread again next refresh.
    }
  }

  async function markAllRead() {
    items.value.forEach((n) => { n.is_read = true })
    unreadCount.value = 0
    try {
      await apiClient.post(`${basePath}/mark-all-read/`)
    } catch {
      // Best-effort - if this fails, it just shows unread again next refresh.
    }
  }

  return { unreadCount, items, loading, refreshCount, loadList, markRead, markAllRead }
}
