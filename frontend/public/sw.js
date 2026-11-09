// Service worker - two jobs: Web Push (a push arriving while no tab is open, and the click that
// follows) and the offline/installable-app behaviour. Registered from
// src/utils/pushNotifications.js; kept as a plain static file (not bundled by Vite) since a
// service worker has to be served from the site's own root to control the whole origin.
//
// Caching rules, deliberately narrow:
//   /api/**          never touched - bookings, payments and auth must always be live, and a
//                    cached API response could show one user another's data on a shared phone.
//   /assets/**       cache-first. Vite gives these hashed filenames, so a cached copy can never
//                    be stale (nginx already serves them as immutable for the same reason).
//   page loads       network-first. Every visit gets the current deploy's HTML; only when the
//                    network fails do we fall back to offline.html, rather than a cached SPA shell
//                    whose API calls would all fail anyway.
//   icons/manifest   precached so the installed app's icon and offline page work offline.
//   anything else    (other origins, POSTs, Django /static/, /media/) passed straight through.
//
// Bump CACHE_VERSION whenever the precache list or offline.html changes - activate() deletes
// every cache that doesn't carry the current name.

const CACHE_VERSION = 'v1'
const PRECACHE = `silverlake-precache-${CACHE_VERSION}`
const ASSETS = `silverlake-assets-${CACHE_VERSION}`
const OFFLINE_URL = '/offline.html'

const PRECACHE_URLS = [
  OFFLINE_URL,
  '/manifest.json',
  '/favicon.png',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(PRECACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  const keep = new Set([PRECACHE, ASSETS])
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => !keep.has(name)).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  )
})

async function networkFirstPage(request) {
  try {
    return await fetch(request)
  } catch {
    const offline = await caches.match(OFFLINE_URL)
    return offline || Response.error()
  }
}

async function cacheFirstAsset(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const cache = await caches.open(ASSETS)
    cache.put(request, response.clone())
  }
  return response
}

async function precachedOrNetwork(request) {
  const cached = await caches.match(request, { cacheName: PRECACHE })
  if (!cached) return fetch(request)
  // Serve the cached copy, but refresh it in the background so a changed icon is picked up.
  fetch(request)
    .then((response) => response.ok && caches.open(PRECACHE).then((cache) => cache.put(request, response)))
    .catch(() => {})
  return cached
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstPage(request))
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirstAsset(request))
  } else if (PRECACHE_URLS.includes(url.pathname)) {
    event.respondWith(precachedOrNetwork(request))
  }
})

self.addEventListener('push', (event) => {
  let data = { title: 'SilverLake Car Rentals', body: '' }
  try {
    if (event.data) data = { ...data, ...event.data.json() }
  } catch {
    if (event.data) data.body = event.data.text()
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/favicon.png',
      badge: '/favicon.png',
      data: { url: data.url || '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.focus()
          if ('navigate' in client) client.navigate(url)
          return
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url)
    }),
  )
})
