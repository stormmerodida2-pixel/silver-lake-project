<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

import apiClient from '../../api/client'

// Vite doesn't resolve Leaflet's default marker image URLs correctly out of the box - point
// them at the actual bundled asset URLs instead.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const LIVE_WINDOW_MS = 15 * 60 * 1000 // a fix newer than this counts as "live"
const KISUMU_CENTER = [-0.0917, 34.7680]

const vehicles = ref([])
const loading = ref(true)
const error = ref('')
const mapEl = ref(null)
let map = null
const markers = []

function isLive(vehicle) {
  if (!vehicle.last_location_at) return false
  return Date.now() - new Date(vehicle.last_location_at).getTime() < LIVE_WINDOW_MS
}

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function renderMarkers() {
  markers.forEach((m) => m.remove())
  markers.length = 0

  const located = vehicles.value.filter((v) => v.last_location_lat && v.last_location_lng)
  located.forEach((vehicle) => {
    const marker = L.marker([vehicle.last_location_lat, vehicle.last_location_lng], {
      opacity: isLive(vehicle) ? 1 : 0.55,
    }).addTo(map)
    marker.bindPopup(`
      <strong>${vehicle.name}</strong><br>
      ${vehicle.driver_name || 'Company fleet'}<br>
      <span style="color:${isLive(vehicle) ? '#16a34a' : '#94a3b8'}">
        ${isLive(vehicle) ? '● Live' : '○ Last seen'} &middot; ${timeAgo(vehicle.last_location_at)}
      </span>
    `)
    markers.push(marker)
  })

  if (located.length) {
    const bounds = L.latLngBounds(located.map((v) => [v.last_location_lat, v.last_location_lng]))
    map.fitBounds(bounds.pad(0.3))
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    // The map should show the whole fleet at once, unlike the paginated Fleet table - follow
    // every `next` page rather than exposing a "Load More" button here.
    let url = '/admin/fleet/'
    const all = []
    while (url) {
      const { data } = await apiClient.get(url)
      all.push(...(data.results ?? data))
      url = data.next ?? null
    }
    vehicles.value = all
    renderMarkers()
  } catch (err) {
    error.value = 'Could not load fleet locations.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  map = L.map(mapEl.value).setView(KISUMU_CENTER, 12)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map)
  load()
})

onBeforeUnmount(() => {
  if (map) map.remove()
})
</script>

<template>
  <div>
    <div>
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Fleet Map</h1>
      <p class="mt-1 text-sm text-slate-400">
        Live position reported by whichever driver has an active trip in a vehicle right now -
        only works while they have the Driver Portal open in their browser, so gaps are expected.
      </p>
    </div>

    <p v-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div class="mt-6 overflow-hidden rounded-xl border border-navy-800">
      <div ref="mapEl" class="h-[480px] w-full"></div>
    </div>

    <div class="mt-6 rounded-xl border border-navy-800">
      <div class="border-b border-navy-800 px-4 py-3 text-sm font-semibold text-slate-300">
        Vehicles without a recent position
      </div>
      <p v-if="loading" class="p-4 text-sm text-slate-400">Loading...</p>
      <ul v-else class="divide-y divide-navy-800">
        <li
          v-for="vehicle in vehicles.filter((v) => !v.last_location_lat)"
          :key="vehicle.id"
          class="flex items-center justify-between px-4 py-3 text-sm"
        >
          <span class="text-slate-200">{{ vehicle.name }}</span>
          <span class="text-xs text-slate-500">{{ vehicle.driver_name || 'Company fleet' }} &middot; no position reported yet</span>
        </li>
        <li v-if="!loading && vehicles.every((v) => v.last_location_lat)" class="px-4 py-3 text-sm text-slate-500">
          Every vehicle has reported a position at some point.
        </li>
      </ul>
    </div>
  </div>
</template>
