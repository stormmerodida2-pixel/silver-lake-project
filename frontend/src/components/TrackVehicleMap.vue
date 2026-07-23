<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

import apiClient from '../api/client'

// Vite doesn't resolve Leaflet's default marker image URLs correctly out of the box - point
// them at the actual bundled asset URLs instead (same fix as AdminFleetMapView.vue).
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const props = defineProps({
  bookingId: { type: [Number, String], required: true },
})

const POLL_INTERVAL_MS = 30000 // matches the admin Fleet Map's own refresh cadence
const LIVE_WINDOW_MS = 15 * 60 * 1000 // a fix newer than this counts as "live"

const loading = ref(true)
const error = ref('')
const trackingAvailable = ref(false)
const lastLocationAt = ref(null)
const driverName = ref('')
const mapEl = ref(null)
let map = null
let marker = null
let pollTimer = null

const isLive = computed(() => {
  if (!lastLocationAt.value) return false
  return Date.now() - new Date(lastLocationAt.value).getTime() < LIVE_WINDOW_MS
})

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function renderPosition(lat, lng) {
  if (!map) {
    map = L.map(mapEl.value).setView([lat, lng], 14)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map)
    marker = L.marker([lat, lng]).addTo(map)
  } else {
    marker.setLatLng([lat, lng])
    map.panTo([lat, lng])
  }
}

async function load() {
  error.value = ''
  try {
    const { data } = await apiClient.get(`/bookings/${props.bookingId}/location/`)
    trackingAvailable.value = data.tracking_available
    if (data.tracking_available) {
      lastLocationAt.value = data.last_location_at
      driverName.value = data.driver_name || ''
      await nextTick()
      renderPosition(data.last_location_lat, data.last_location_lng)
    } else if (map) {
      // The trip ended (or hasn't started) since the last poll - drop the stale map rather
      // than leave a frozen pin on screen.
      map.remove()
      map = null
      marker = null
    }
  } catch {
    error.value = "Could not check the vehicle's location."
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  pollTimer = setInterval(load, POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  clearInterval(pollTimer)
  if (map) map.remove()
})
</script>

<template>
  <div class="rounded-lg border border-slate-200 bg-white p-4">
    <p v-if="loading" class="text-sm text-slate-500">Checking for a live location...</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>
    <template v-else-if="trackingAvailable">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-sm font-semibold">
          <span :class="isLive ? 'text-green-600' : 'text-slate-400'">{{ isLive ? '● Live' : '○ Last seen' }}</span>
          <span class="text-slate-500"> &middot; {{ timeAgo(lastLocationAt) }}</span>
        </p>
        <p v-if="driverName" class="text-xs text-slate-500">Driver: {{ driverName }}</p>
      </div>
      <div ref="mapEl" class="mt-3 h-56 w-full overflow-hidden rounded-md"></div>
    </template>
    <p v-else class="text-sm text-slate-500">
      Live tracking isn't available yet - it turns on once your driver starts reporting their position for this trip.
    </p>
  </div>
</template>
