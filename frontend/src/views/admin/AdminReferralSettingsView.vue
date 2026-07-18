<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'

const loading = ref(true)
const error = ref('')
const saving = ref(false)
const saveError = ref('')
const saved = ref(false)

const creditAmount = ref('')
const stats = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.get('/admin/referral-settings/')
    creditAmount.value = data.credit_amount
    stats.value = data
  } catch (err) {
    error.value = 'Could not load referral settings.'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  saveError.value = ''
  saved.value = false
  try {
    const { data } = await apiClient.patch('/admin/referral-settings/', { credit_amount: creditAmount.value })
    stats.value = data
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (err) {
    saveError.value = err.response?.data?.credit_amount?.[0] || 'Could not save this change.'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Referral Program</h1>
    <p class="mt-1 text-sm text-slate-400">
      Set the KES amount a customer earns once a friend they referred completes their first
      confirmed booking. Changing it only affects credits awarded from that point on.
    </p>

    <p v-if="loading" class="mt-6 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-6 text-center text-red-400">{{ error }}</p>

    <template v-else>
      <div class="mt-6 max-w-md rounded-xl border border-navy-800 bg-navy-900 p-6">
        <label class="mb-1.5 block text-sm font-medium text-slate-300">Credit amount (KES)</label>
        <div class="flex gap-3">
          <input
            v-model="creditAmount"
            type="number"
            min="1"
            step="1"
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
          <button
            :disabled="saving"
            class="shrink-0 rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
            @click="save"
          >
            {{ saving ? 'Saving...' : (saved ? 'Saved!' : 'Save') }}
          </button>
        </div>
        <p v-if="saveError" class="mt-2 text-sm text-red-400">{{ saveError }}</p>
      </div>

      <div class="mt-6 grid gap-4 sm:grid-cols-3">
        <div class="rounded-xl border border-navy-800 p-5">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Credits Awarded</p>
          <p class="mt-1 font-[Georgia] text-2xl font-bold text-white">
            KES {{ Number(stats.credits_awarded_total).toLocaleString() }}
          </p>
          <p class="mt-1 text-xs text-slate-500">{{ stats.credits_awarded_count }} credit{{ stats.credits_awarded_count === 1 ? '' : 's' }}</p>
        </div>
        <div class="rounded-xl border border-navy-800 p-5">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Redeemed</p>
          <p class="mt-1 font-[Georgia] text-2xl font-bold text-emerald-400">
            KES {{ Number(stats.credits_redeemed_total).toLocaleString() }}
          </p>
          <p class="mt-1 text-xs text-slate-500">{{ stats.credits_redeemed_count }} credit{{ stats.credits_redeemed_count === 1 ? '' : 's' }}</p>
        </div>
        <div class="rounded-xl border border-navy-800 p-5">
          <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Outstanding</p>
          <p class="mt-1 font-[Georgia] text-2xl font-bold text-gold-400">
            KES {{ Number(stats.credits_outstanding_total).toLocaleString() }}
          </p>
          <p class="mt-1 text-xs text-slate-500">Not yet redeemed</p>
        </div>
      </div>
    </template>
  </div>
</template>
