<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'

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
  debug_mode: 'Debug Mode',
}

async function load() {
  try {
    const { data } = await apiClient.get('/admin/health/')
    checks.value = data
    error.value = ''
  } catch (err) {
    error.value = 'Could not load system health.'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function refresh() {
  refreshing.value = true
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">System Health</h1>
      <button
        :disabled="refreshing"
        class="rounded-md border border-navy-700 px-3 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
        @click="refresh"
      >
        {{ refreshing ? 'Checking...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="loading" class="text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="text-center text-red-400">{{ error }}</p>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="(key) in Object.keys(labels)"
        :key="key"
        class="rounded-xl border p-5"
        :class="checks[key]?.ok ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'"
      >
        <div class="flex items-center gap-2">
          <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="checks[key]?.ok ? 'bg-emerald-400' : 'bg-red-400'" />
          <h2 class="font-semibold text-white">{{ labels[key] }}</h2>
        </div>
        <p class="mt-2 text-sm" :class="checks[key]?.ok ? 'text-emerald-300' : 'text-red-300'">
          {{ checks[key]?.ok ? 'OK' : 'Attention needed' }}
        </p>
        <p v-if="checks[key]?.detail" class="mt-1 text-xs text-slate-400">{{ checks[key].detail }}</p>
        <p v-if="checks[key]?.environment" class="mt-1 text-xs text-slate-500">Environment: {{ checks[key].environment }}</p>
        <p v-if="checks[key]?.engine" class="mt-1 text-xs text-slate-500">Engine: {{ checks[key].engine }}</p>
        <p v-if="checks[key]?.error" class="mt-1 text-xs text-red-400">{{ checks[key].error }}</p>
      </div>
    </div>
  </div>
</template>
