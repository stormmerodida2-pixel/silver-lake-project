<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import RevenueTrendChart from '../../components/admin/RevenueTrendChart.vue'
import TopVehiclesChart from '../../components/admin/TopVehiclesChart.vue'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const showRevenueTable = ref(false)
const showVehiclesTable = ref(false)

function monthLabel(monthStr) {
  const [year, month] = monthStr.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

onMounted(async () => {
  try {
    const { data: response } = await apiClient.get('/admin/analytics/')
    data.value = response
  } catch {
    error.value = 'Could not load analytics.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Analytics</h1>
    <p class="mt-1 text-sm text-slate-400">Revenue, fleet, and customer trends over the last 12 months.</p>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-else class="mt-6 space-y-6">
      <section class="rounded-2xl border border-navy-800 bg-navy-900 p-6">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Revenue Collected</h2>
          <button
            class="text-xs font-semibold text-slate-400 hover:text-gold-400"
            @click="showRevenueTable = !showRevenueTable"
          >
            {{ showRevenueTable ? 'View Chart' : 'View as Table' }}
          </button>
        </div>

        <RevenueTrendChart v-if="!showRevenueTable" :data="data.revenue_trend" class="mt-4" />
        <div v-else class="mt-4 overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="text-slate-400">
              <tr>
                <th class="py-1.5 pr-4 font-medium">Month</th>
                <th class="py-1.5 font-medium">Revenue (KES)</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-navy-800">
              <tr v-for="month in data.revenue_trend" :key="month.month">
                <td class="py-1.5 pr-4 text-slate-300">{{ monthLabel(month.month) }}</td>
                <td class="py-1.5 text-white" style="font-variant-numeric: tabular-nums">
                  {{ Number(month.revenue).toLocaleString() }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid gap-6 lg:grid-cols-2">
        <section class="rounded-2xl border border-navy-800 bg-navy-900 p-6">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Top Vehicles by Revenue</h2>
            <button
              v-if="data.top_vehicles.length"
              class="text-xs font-semibold text-slate-400 hover:text-gold-400"
              @click="showVehiclesTable = !showVehiclesTable"
            >
              {{ showVehiclesTable ? 'View Chart' : 'View as Table' }}
            </button>
          </div>

          <TopVehiclesChart v-if="!showVehiclesTable" :data="data.top_vehicles" class="mt-4" />
          <div v-else class="mt-4 overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="text-slate-400">
                <tr>
                  <th class="py-1.5 pr-4 font-medium">Vehicle</th>
                  <th class="py-1.5 pr-4 font-medium">Bookings</th>
                  <th class="py-1.5 font-medium">Revenue (KES)</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-navy-800">
                <tr v-for="vehicle in data.top_vehicles" :key="vehicle.id">
                  <td class="py-1.5 pr-4 text-slate-300">{{ vehicle.name }}</td>
                  <td class="py-1.5 pr-4 text-slate-300" style="font-variant-numeric: tabular-nums">
                    {{ vehicle.bookings }}
                  </td>
                  <td class="py-1.5 text-white" style="font-variant-numeric: tabular-nums">
                    {{ Number(vehicle.revenue).toLocaleString() }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="rounded-2xl border border-navy-800 bg-navy-900 p-6">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">New vs Repeat Customers</h2>
          <div class="mt-4 grid grid-cols-2 gap-4">
            <div>
              <p class="text-xs text-slate-500">Repeat Rate</p>
              <p class="mt-1 text-3xl font-bold text-white">{{ data.customers.repeat_rate }}%</p>
            </div>
            <div>
              <p class="text-xs text-slate-500">Total Customers</p>
              <p class="mt-1 text-3xl font-bold text-white">{{ data.customers.new + data.customers.repeat }}</p>
            </div>
          </div>

          <div v-if="data.customers.new + data.customers.repeat > 0" class="mt-6">
            <div class="mb-2 flex items-center gap-4 text-xs">
              <span class="flex items-center gap-1.5 text-slate-300">
                <span class="h-2.5 w-2.5 rounded-full" style="background: #96751e"></span> Repeat ({{
                  data.customers.repeat
                }})
              </span>
              <span class="flex items-center gap-1.5 text-slate-300">
                <span class="h-2.5 w-2.5 rounded-full" style="background: #2f6fed"></span> New ({{
                  data.customers.new
                }})
              </span>
            </div>
            <div class="flex h-6 w-full gap-0.5 overflow-hidden rounded-full bg-navy-950">
              <div
                class="flex items-center justify-center text-[10px] font-semibold text-navy-950"
                :style="{ width: `${data.customers.repeat_rate}%`, background: '#96751e' }"
              >
                <span v-if="data.customers.repeat_rate >= 15">{{ data.customers.repeat_rate }}%</span>
              </div>
              <div
                class="flex items-center justify-center text-[10px] font-semibold text-white"
                :style="{ width: `${100 - data.customers.repeat_rate}%`, background: '#2f6fed' }"
              >
                <span v-if="100 - data.customers.repeat_rate >= 15"
                  >{{ (100 - data.customers.repeat_rate).toFixed(1) }}%</span
                >
              </div>
            </div>
          </div>
          <p v-else class="mt-6 text-sm text-slate-500">No confirmed bookings in the last 12 months yet.</p>
        </section>
      </div>
    </div>
  </div>
</template>
