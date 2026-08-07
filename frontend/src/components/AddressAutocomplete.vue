<script setup>
// inheritAttrs: false - passthrough attributes like `required` need to land on the actual
// <input> below, not on this component's wrapping <div> (where `required` would be invalid/inert).
defineOptions({ inheritAttrs: false })

import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

// Vite doesn't resolve Leaflet's default marker image URLs correctly out of the box - same fix
// as TrackVehicleMap.vue/AdminFleetMapView.vue.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

// Same bias point as AdminFleetMapView.vue's own KISUMU_CENTER - duplicated here (not extracted
// to a shared file) since it's two numbers used in two places and this codebase has no existing
// shared-constants module.
const KISUMU_LAT = -0.0917
const KISUMU_LNG = 34.768

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const suggestions = ref([])
const showDropdown = ref(false)
const selected = ref(null) // { lat, lng } | null, mirrors what's emitted via 'select'
const mapEl = ref(null)
let map = null
let debounceTimer = null

function labelFor(properties) {
  const parts = [
    properties.name,
    properties.street,
    properties.city || properties.district || properties.county,
    properties.state,
    properties.country,
  ]
  // Photon returns a different subset of these per feature type (a street vs. a POI vs. an
  // admin area) - join whichever are actually present, and dedupe (e.g. name === city for a
  // town-level result) rather than showing "Kisumu, Kisumu".
  return [...new Set(parts.filter(Boolean))].join(', ')
}

async function search(query) {
  if (!query || query.trim().length < 3) {
    suggestions.value = []
    showDropdown.value = false
    return
  }
  try {
    // Photon (photon.komoot.io) - a free, no-API-key OSM-based geocoder purpose-built for
    // search-as-you-type autocomplete (unlike raw Nominatim, whose usage policy explicitly
    // prohibits this exact usage pattern and caps at 1 request/second). Free community service
    // with no uptime guarantee - if booking volume grows enough to matter, self-hosting Photon
    // is the natural next step. Biased (not hard-filtered) toward Kisumu, since a customer might
    // legitimately book an airport transfer or a pickup in a neighboring town.
    const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&lat=${KISUMU_LAT}&lon=${KISUMU_LNG}&limit=5`
    // Deliberately a bare fetch(), not the app's own apiClient (see ../api/client.js) - that
    // instance's request interceptor unconditionally attaches the customer's live JWT to every
    // request it makes, including absolute-URL requests to third-party hosts. Using it here
    // would leak the access token to Komoot's servers on every keystroke.
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    suggestions.value = (data.features || [])
      .map((feature) => ({
        label: labelFor(feature.properties || {}),
        // GeoJSON coordinate order is [lon, lat] - the opposite of lat/lng order used
        // everywhere else in this codebase. Confirmed against Photon's live response shape.
        // Rounded to 6 decimal places (~11cm precision) - Photon returns more precision than
        // that, which the backend's DecimalField(max_digits=9, decimal_places=6) rejects
        // outright (confirmed live: a raw Photon value 400s the booking with "Ensure that there
        // are no more than 6 decimal places"). Matches Vehicle.last_location_lat/lng's own
        // precision exactly.
        lat: Math.round(feature.geometry.coordinates[1] * 1e6) / 1e6,
        lng: Math.round(feature.geometry.coordinates[0] * 1e6) / 1e6,
      }))
      .filter((s) => s.label)
    showDropdown.value = suggestions.value.length > 0
  } catch {
    // Network error, CSP block, CORS failure, bad JSON - all treated the same: no suggestions,
    // the input keeps working as a plain text field. Never block typing or submitting a booking
    // over this free third-party service being unavailable.
    suggestions.value = []
    showDropdown.value = false
  }
}

function clearSelection() {
  if (!selected.value) return
  selected.value = null
  emit('select', null)
  removeMap()
}

function onInput(event) {
  const value = event.target.value
  emit('update:modelValue', value)
  clearSelection()
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(value), 300)
}

async function choose(suggestion) {
  emit('update:modelValue', suggestion.label)
  suggestions.value = []
  showDropdown.value = false
  selected.value = { lat: suggestion.lat, lng: suggestion.lng }
  emit('select', selected.value)
  await nextTick() // the map container only exists in the DOM once `selected` is truthy
  renderMap(suggestion.lat, suggestion.lng)
}

function renderMap(lat, lng) {
  if (!mapEl.value) return
  map = L.map(mapEl.value).setView([lat, lng], 15)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map)
  // No need to track the marker separately - map.remove() below tears down every layer on it,
  // marker included, and each new selection fully recreates the map rather than repositioning
  // an existing marker (the DOM node itself gets destroyed/recreated by the v-if in the
  // template, so there's never a live map instance to update in place).
  L.marker([lat, lng]).addTo(map)
}

function removeMap() {
  if (map) {
    map.remove()
    map = null
  }
}

function blurSoon() {
  // Delay so a click on a dropdown item (@mousedown) registers before blur hides the dropdown.
  setTimeout(() => {
    showDropdown.value = false
  }, 150)
}

watch(
  () => props.modelValue,
  (value) => {
    // Parent cleared the field externally (e.g. resetting the whole booking form) - drop any
    // stale selection/map along with it.
    if (!value) clearSelection()
  },
)

onBeforeUnmount(removeMap)
</script>

<template>
  <div class="relative">
    <input
      v-bind="$attrs"
      type="text"
      :value="modelValue"
      autocomplete="off"
      class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
      @input="onInput"
      @focus="showDropdown = suggestions.length > 0"
      @blur="blurSoon"
    />
    <ul
      v-if="showDropdown"
      class="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-surface-2 shadow-lg"
    >
      <li
        v-for="(suggestion, index) in suggestions"
        :key="index"
        class="cursor-pointer px-3 py-2 text-sm text-foreground hover:bg-border"
        @mousedown.prevent="choose(suggestion)"
      >
        {{ suggestion.label }}
      </li>
    </ul>
    <div v-if="selected" class="mt-2 overflow-hidden rounded-md border border-border">
      <div ref="mapEl" class="h-40 w-full"></div>
    </div>
  </div>
</template>
