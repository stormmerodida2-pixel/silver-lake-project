<script setup>
import { onMounted } from 'vue'

import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: entries, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/audit-log/')

function formatDate(value) {
  return new Date(value).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' })
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Activity Log</h1>
    <p v-if="auth.user?.organization_name" class="mt-1 text-sm text-foreground-muted">
      Who did what within {{ auth.user.organization_name }}: role changes, suspensions, verified/paid payouts, and
      issued refunds.
    </p>
    <p v-else class="mt-1 text-sm text-foreground-muted">
      Who did what: role changes, suspensions, verified/paid payouts, and issued refunds.
    </p>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 overflow-x-auto rounded-xl border border-border-subtle">
        <table class="w-full text-left text-sm">
          <thead class="bg-surface text-foreground-muted">
            <tr>
              <th class="px-4 py-3">When</th>
              <th class="px-4 py-3">Admin</th>
              <th class="px-4 py-3">Action</th>
              <th class="px-4 py-3">Target</th>
              <th v-if="!auth.user?.organization_name" class="px-4 py-3">Organization</th>
              <th class="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-subtle bg-page">
            <tr v-for="entry in entries" :key="entry.id">
              <td class="px-4 py-3 whitespace-nowrap text-foreground-muted">{{ formatDate(entry.created_at) }}</td>
              <td class="px-4 py-3 text-foreground">{{ entry.actor_email || 'Unknown' }}</td>
              <td class="px-4 py-3 text-accent">{{ entry.action }}</td>
              <td class="px-4 py-3 text-foreground-secondary">{{ entry.target_repr }}</td>
              <td v-if="!auth.user?.organization_name" class="px-4 py-3 text-foreground-muted">
                {{ entry.organization_name || 'Platform' }}
              </td>
              <td class="px-4 py-3 text-foreground-muted">{{ entry.detail || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!entries.length" class="p-6 text-center text-foreground-muted">No admin activity recorded yet.</p>
        <div v-if="nextUrl" class="border-t border-border-subtle p-3 text-center">
          <button
            :disabled="loadingMore"
            class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
            @click="loadMore"
          >
            {{ loadingMore ? 'Loading...' : 'Load More' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
