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
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Activity Log</h1>
    <p v-if="auth.user?.organization_name" class="mt-1 text-sm text-slate-400">
      Who did what within {{ auth.user.organization_name }}: role changes, suspensions,
      verified/paid payouts, and issued refunds.
    </p>
    <p v-else class="mt-1 text-sm text-slate-400">
      Who did what: role changes, suspensions, verified/paid payouts, and issued refunds.
    </p>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 overflow-x-auto rounded-xl border border-navy-800">
        <table class="w-full text-left text-sm">
          <thead class="bg-navy-900 text-slate-400">
            <tr>
              <th class="px-4 py-3">When</th>
              <th class="px-4 py-3">Admin</th>
              <th class="px-4 py-3">Action</th>
              <th class="px-4 py-3">Target</th>
              <th v-if="!auth.user?.organization_name" class="px-4 py-3">Organization</th>
              <th class="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-navy-800 bg-navy-950">
            <tr v-for="entry in entries" :key="entry.id">
              <td class="px-4 py-3 whitespace-nowrap text-slate-400">{{ formatDate(entry.created_at) }}</td>
              <td class="px-4 py-3 text-white">{{ entry.actor_email || 'Unknown' }}</td>
              <td class="px-4 py-3 text-gold-400">{{ entry.action }}</td>
              <td class="px-4 py-3 text-slate-300">{{ entry.target_repr }}</td>
              <td v-if="!auth.user?.organization_name" class="px-4 py-3 text-slate-400">{{ entry.organization_name || 'Platform' }}</td>
              <td class="px-4 py-3 text-slate-400">{{ entry.detail || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!entries.length" class="p-6 text-center text-slate-400">No admin activity recorded yet.</p>
        <div v-if="nextUrl" class="border-t border-navy-800 p-3 text-center">
          <button
            :disabled="loadingMore"
            class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
            @click="loadMore"
          >
            {{ loadingMore ? 'Loading...' : 'Load More' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
