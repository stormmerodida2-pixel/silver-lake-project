import apiClient from '../api/client'

// The Push API's applicationServerKey wants raw bytes, not the base64url string the backend
// hands back - standard conversion, same one every Web Push tutorial uses.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)))
}

export function isPushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window
}

// Registering alone never prompts anything - safe to call unconditionally on every page load
// (see main.js) so the worker is already active by the time someone actually opts in.
export async function registerServiceWorker() {
  if (!isPushSupported()) return null
  try {
    return await navigator.serviceWorker.register('/sw.js')
  } catch {
    return null
  }
}

// 'unsupported' | 'denied' | 'subscribed' | 'unsubscribed'
export async function getPushSubscriptionStatus() {
  if (!isPushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  const registration = await navigator.serviceWorker.ready.catch(() => null)
  if (!registration) return 'unsubscribed'
  const subscription = await registration.pushManager.getSubscription()
  return subscription ? 'subscribed' : 'unsubscribed'
}

// Requesting permission has to happen from a real user gesture (a click), never on page load -
// call this from a button handler, not automatically.
export async function enablePushNotifications() {
  if (!isPushSupported()) throw new Error('Push notifications are not supported in this browser.')

  const { data } = await apiClient.get('/push/vapid-public-key/')
  if (!data.public_key) throw new Error('Push notifications are not configured.')

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notification permission was not granted.')

  const registration = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(data.public_key),
  })

  const json = subscription.toJSON()
  await apiClient.post('/push/subscription/', { endpoint: json.endpoint, keys: json.keys })
  return subscription
}

export async function disablePushNotifications() {
  if (!isPushSupported()) return
  const registration = await navigator.serviceWorker.ready.catch(() => null)
  if (!registration) return
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) return
  await apiClient.delete('/push/subscription/', { data: { endpoint: subscription.endpoint } })
  await subscription.unsubscribe()
}
