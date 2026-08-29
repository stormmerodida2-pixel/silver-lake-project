// Per-browser, not per-account - a customer browsing before they've logged in (or never does)
// still gets the benefit, and it survives across sessions the same way a cart would. No backend
// involved at all: this only ever stores vehicle IDs, and the actual vehicle data is always
// re-read fresh from wherever the caller already has it loaded (useCatalogStore's cache).
const STORAGE_KEY = 'sl_recently_viewed_vehicles'
const MAX_ENTRIES = 8

function readIds() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// Call once a vehicle detail page has actually loaded - moves it to the front if already
// present (most-recently-viewed first), rather than storing duplicate/stale entries.
export function recordVehicleView(vehicleId) {
  try {
    const ids = readIds().filter((id) => id !== vehicleId)
    ids.unshift(vehicleId)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids.slice(0, MAX_ENTRIES)))
  } catch {
    // Private browsing / storage disabled / quota exceeded - not worth surfacing an error over
    // a purely cosmetic feature.
  }
}

// excludeId lets a vehicle's own detail page ask for "recently viewed" without listing itself.
export function getRecentlyViewedIds(excludeId) {
  return readIds().filter((id) => id !== excludeId)
}
