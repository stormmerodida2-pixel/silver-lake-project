<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const checks = ref(null)
const loading = ref(true)
const error = ref('')
const refreshing = ref(false)

const labels = {
  database: 'Database',
  email: 'Email',
  mpesa: 'M-Pesa',
  storage: 'File Storage',
  scheduler: 'Background Sweeps',
  error_tracking: 'Error Tracking',
  debug_mode: 'Debug Mode',
}

async function load() {
  try {
    const { data } = await apiClient.get('/admin/health/')
    checks.value = data
    error.value = ''
  } catch {
    error.value = 'Could not load system health.'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function refresh() {
  refreshing.value = true
  load()
  loadErrorReports()
}

const {
  items: errorReportItems,
  nextUrl: errorReportsNextUrl,
  loading: errorReportsLoading,
  loadingMore: errorReportsLoadingMore,
  error: errorReportsError,
  load: loadErrorReports,
  loadMore: loadMoreErrorReports,
} = useAdminList('/admin/client-errors/')
const expandedReportId = ref(null)

function formatDate(value) {
  return new Date(value).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' })
}

function toggleExpanded(id) {
  expandedReportId.value = expandedReportId.value === id ? null : id
}

onMounted(() => {
  load()
  loadErrorReports()
})
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-foreground">System Health</h1>
      <button
        :disabled="refreshing"
        class="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
        @click="refresh"
      >
        {{ refreshing ? 'Checking...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="loading" class="text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="text-center text-danger">{{ error }}</p>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="key in Object.keys(labels)"
        :key="key"
        class="rounded-xl border p-5"
        :class="checks[key]?.ok ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'"
      >
        <div class="flex items-center gap-2">
          <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="checks[key]?.ok ? 'bg-emerald-400' : 'bg-red-400'" />
          <h2 class="font-semibold text-foreground">{{ labels[key] }}</h2>
        </div>
        <p class="mt-2 text-sm" :class="checks[key]?.ok ? 'text-emerald-300' : 'text-red-300'">
          {{ checks[key]?.ok ? 'OK' : 'Attention needed' }}
        </p>
        <p v-if="checks[key]?.detail" class="mt-1 text-xs text-foreground-muted">{{ checks[key].detail }}</p>
        <p v-if="checks[key]?.environment" class="mt-1 text-xs text-foreground-subtle">
          Environment: {{ checks[key].environment }}
        </p>
        <p v-if="checks[key]?.engine" class="mt-1 text-xs text-foreground-subtle">Engine: {{ checks[key].engine }}</p>
        <p v-if="checks[key]?.error" class="mt-1 text-xs text-danger">{{ checks[key].error }}</p>
      </div>
    </div>

    <div class="mt-10">
      <h2 class="font-[Georgia] text-xl font-bold text-foreground">Recent Errors</h2>
      <p class="mt-1 text-sm text-foreground-muted">
        Everything worth a superadmin's attention, not just what a visitor happened to hit: frontend JS crashes and
        failed API requests reported by visitors' browsers, plus background sweep failures (stale-payment cleanup,
        escalation reminders, etc.) that have no user or request to report themselves - previously only ever visible
        via server logs.
      </p>

      <p v-if="errorReportsLoading" class="mt-6 text-center text-foreground-muted">Loading...</p>
      <p v-else-if="errorReportsError" class="mt-4 text-sm text-danger">{{ errorReportsError }}</p>

      <template v-else>
        <div class="mt-4 overflow-x-auto rounded-xl border border-border-subtle">
          <table class="w-full text-left text-sm">
            <thead class="bg-surface text-foreground-muted">
              <tr>
                <th class="px-4 py-3">When</th>
                <th class="px-4 py-3">Source</th>
                <th class="px-4 py-3">Client</th>
                <th class="px-4 py-3">Message</th>
                <th class="px-4 py-3">Page</th>
                <th class="px-4 py-3" />
              </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle bg-page">
              <template v-for="report in errorReportItems" :key="report.id">
                <tr>
                  <td class="px-4 py-3 whitespace-nowrap text-foreground-muted">{{ formatDate(report.created_at) }}</td>
                  <td class="px-4 py-3">
                    <span
                      class="rounded-full px-2 py-0.5 text-xs font-semibold"
                      :class="
                        report.source === 'scheduler'
                          ? 'bg-brand-blue-500/10 text-brand-blue-400'
                          : 'bg-surface-2 text-foreground-secondary'
                      "
                    >
                      {{ report.source_display }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-foreground">
                    {{ report.source === 'scheduler' ? '-' : report.user_email || 'Anonymous visitor' }}
                  </td>
                  <td class="px-4 py-3 text-red-300">{{ report.message }}</td>
                  <td class="px-4 py-3 text-foreground-muted">
                    <span class="break-all">{{ report.url || '-' }}</span>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <button
                      class="text-xs font-medium text-accent hover:underline"
                      @click="toggleExpanded(report.id)"
                    >
                      {{ expandedReportId === report.id ? 'Hide' : 'Details' }}
                    </button>
                  </td>
                </tr>
                <tr v-if="expandedReportId === report.id">
                  <td colspan="6" class="border-t border-border-subtle bg-surface/50 px-4 py-3">
                    <p class="text-xs text-foreground-muted">User-Agent: {{ report.user_agent || 'Unknown' }}</p>
                    <pre
                      v-if="report.stack"
                      class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs text-foreground-secondary"
                      >{{ report.stack }}</pre>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
          <p v-if="!errorReportItems.length" class="p-6 text-center text-foreground-muted">No errors reported.</p>
          <div v-if="errorReportsNextUrl" class="border-t border-border-subtle p-3 text-center">
            <button
              :disabled="errorReportsLoadingMore"
              class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="loadMoreErrorReports"
            >
              {{ errorReportsLoadingMore ? 'Loading...' : 'Load More' }}
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
