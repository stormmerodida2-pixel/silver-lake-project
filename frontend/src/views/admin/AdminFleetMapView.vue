<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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
const POLL_INTERVAL_MS = 30000 // matches NotificationBell's own refresh cadence
const KISUMU_CENTER = [-0.0917, 34.768]

const vehicles = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const mapEl = ref(null)
let map = null
let pollTimer = null
const markerById = new Map()

function isLive(vehicle) {
  if (!vehicle.last_location_at) return false
  return Date.now() - new Date(vehicle.last_location_at).getTime() < LIVE_WINDOW_MS
}

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// Live vehicles first, then most-recently-seen, then never-reported - so the vehicles worth
// acting on right now are always at the top of the list instead of needing a scan of the map.
const sortedVehicles = computed(() => {
  const term = search.value.trim().toLowerCase()
  const filtered = term
    ? vehicles.value.filter(
        (v) => v.name.toLowerCase().includes(term) || (v.driver_name || '').toLowerCase().includes(term),
      )
    : vehicles.value

  return [...filtered].sort((a, b) => {
    const aLive = isLive(a)
    const bLive = isLive(b)
    if (aLive !== bLive) return aLive ? -1 : 1
    const aHas = Boolean(a.last_location_at)
    const bHas = Boolean(b.last_location_at)
    if (aHas !== bHas) return aHas ? -1 : 1
    if (aHas && bHas) return new Date(b.last_location_at) - new Date(a.last_location_at)
    return a.name.localeCompare(b.name)
  })
})

function renderMarkers() {
  markerById.forEach((m) => m.remove())
  markerById.clear()

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
    markerById.set(vehicle.id, marker)
  })

  return located
}

// Pans/zooms to a specific vehicle and opens its popup - the point of the list existing at all,
// since finding one pin among a cluster on the map itself doesn't scale past a handful of cars.
function focusVehicle(vehicle) {
  if (!map || !vehicle.last_location_lat || !vehicle.last_location_lng) return
  map.setView([vehicle.last_location_lat, vehicle.last_location_lng], 15)
  markerById.get(vehicle.id)?.openPopup()
}

async function load({ fitBounds } = { fitBounds: false }) {
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
    const located = renderMarkers()
    // Only auto-fit on the initial load and on a manual refresh click - refitting on every
    // silent background poll would yank the view out from under an admin who's zoomed into a
    // specific vehicle.
    if (fitBounds && located.length) {
      const bounds = L.latLngBounds(located.map((v) => [v.last_location_lat, v.last_location_lng]))
      map.fitBounds(bounds.pad(0.3))
    }
  } catch {
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
  load({ fitBounds: true })
  pollTimer = setInterval(() => load({ fitBounds: false }), POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (map) map.remove()
  clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Fleet Map</h1>
        <p class="mt-1 text-sm text-foreground-muted">
          Live position reported by whichever driver has an active trip in a vehicle right now - only works while they
          have the Driver Portal open in their browser, so gaps are expected. Refreshes automatically every 30 seconds.
        </p>
      </div>
      <button
        type="button"
        class="shrink-0 rounded-md border border-border px-3 py-2 text-sm font-semibold text-foreground transition hover:border-accent-border hover:text-accent"
        @click="load({ fitBounds: true })"
      >
        Refresh &amp; recenter
      </button>
    </div>

    <p v-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div class="overflow-hidden rounded-xl border border-border-subtle lg:col-span-2">
        <div ref="mapEl" class="h-[560px] w-full"></div>
      </div>

      <div class="flex flex-col overflow-hidden rounded-xl border border-border-subtle">
        <div class="border-b border-border-subtle px-4 py-3">
          <input
            v-model="search"
            type="text"
            placeholder="Search by vehicle or driver..."
            class="w-full rounded-md border border-border bg-page px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:border-accent-border focus:outline-none"
          />
        </div>
        <p v-if="loading" class="p-4 text-sm text-foreground-muted">Loading...</p>
        <ul v-else class="max-h-[500px] divide-y divide-border-subtle overflow-y-auto">
          <li v-for="vehicle in sortedVehicles" :key="vehicle.id">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-surface-2 disabled:cursor-default disabled:hover:bg-transparent"
              :disabled="!vehicle.last_location_lat"
              @click="focusVehicle(vehicle)"
            >
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium text-foreground">{{ vehicle.name }}</span>
                <span class="block truncate text-xs text-foreground-subtle">{{ vehicle.driver_name || 'Company fleet' }}</span>
              </span>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold"
                :class="
                  isLive(vehicle)
                    ? 'bg-green-500/10 text-success'
                    : vehicle.last_location_at
                      ? 'bg-surface-2 text-foreground-muted'
                      : 'bg-surface-2 text-foreground-subtle'
                "
              >
                {{
                  isLive(vehicle)
                    ? 'Live'
                    : vehicle.last_location_at
                      ? timeAgo(vehicle.last_location_at)
                      : 'No position'
                }}
              </span>
            </button>
          </li>
          <li v-if="!sortedVehicles.length" class="px-4 py-3 text-sm text-foreground-subtle">
            No vehicles match "{{ search }}".
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
