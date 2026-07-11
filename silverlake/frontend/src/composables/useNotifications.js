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
  const mutedEvents = ref([])

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

  async function loadPreferences() {
    try {
      const { data } = await apiClient.get(`${basePath}/preferences/`)
      mutedEvents.value = data.muted_events
    } catch {
      // Silently do nothing - the preferences panel just shows nothing muted yet.
    }
  }

  async function toggleMute(event) {
    const isMuted = mutedEvents.value.includes(event)
    mutedEvents.value = isMuted
      ? mutedEvents.value.filter((e) => e !== event)
      : [...mutedEvents.value, event]
    try {
      await apiClient.post(`${basePath}/${isMuted ? 'unmute' : 'mute'}/`, { event })
    } catch {
      // Best-effort - if this fails, it just reverts next time preferences are loaded.
    }
    // A just-muted event's existing notifications should disappear from the list/count
    // immediately, not wait for the next poll.
    if (!isMuted) {
      items.value = items.value.filter((n) => n.event !== event)
      refreshCount()
    }
  }

  return {
    unreadCount, items, loading, mutedEvents,
    refreshCount, loadList, markRead, markAllRead, loadPreferences, toggleMute,
  }
}
