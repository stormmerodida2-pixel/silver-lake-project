<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const unread = ref([])

async function load() {
  if (!auth.isAuthenticated) return
  try {
    const { data } = await apiClient.get('/announcements/mine/')
    unread.value = data.filter((a) => !a.is_read)
  } catch {
    // Silently do nothing - a missed announcement isn't worth surfacing an error over.
  }
}

async function dismiss(announcement) {
  unread.value = unread.value.filter((a) => a.id !== announcement.id)
  try {
    await apiClient.post(`/announcements/${announcement.id}/mark-read/`)
  } catch {
    // Best-effort - if this fails, it just shows again next visit.
  }
}

onMounted(load)
</script>

<template>
  <div v-if="unread.length" class="space-y-3">
    <div
      v-for="announcement in unread"
      :key="announcement.id"
      class="flex items-start gap-3 rounded-xl border-l-4 border-gold-500 bg-white p-4 shadow-lg shadow-black/10"
    >
      <div class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gold-500/15 text-gold-600">
        <svg class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
        </svg>
      </div>
      <div class="min-w-0 flex-1">
        <p class="text-xs font-semibold uppercase tracking-wide text-gold-600">Announcement</p>
        <p class="mt-0.5 font-semibold text-navy-900">{{ announcement.title }}</p>
        <p class="mt-1 whitespace-pre-line text-sm text-slate-600">{{ announcement.body }}</p>
      </div>
      <button
        class="shrink-0 text-slate-400 transition-colors hover:text-navy-900"
        aria-label="Dismiss"
        @click="dismiss(announcement)"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  </div>
</template>
