// Web Push service worker - handles a push arriving while no tab is open (or focused) and the
// click that follows. Registered from src/utils/pushNotifications.js; kept as a plain static
// file (not bundled by Vite) since a service worker has to be served from the site's own root
// to control the whole origin.

self.addEventListener('push', (event) => {
  let data = { title: 'SilverLake Car Rentals', body: '' }
  try {
    if (event.data) data = { ...data, ...event.data.json() }
  } catch (err) {
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
