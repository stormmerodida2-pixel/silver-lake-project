import { reactive } from 'vue'

// "Install the app" support for InstallAppBanner.vue.
//
// Chrome/Edge/Samsung Internet on Android fire `beforeinstallprompt` once the site qualifies as
// installable (manifest + service worker + HTTPS). We hold on to that event so a button can show
// the native install dialog later - and that event can fire before Vue has even mounted, which is
// why initInstallPrompt() runs from main.js rather than from the banner's own onMounted.
//
// iOS never fires that event at all: the only way to install there is Share -> Add to Home
// Screen, so for iOS the banner shows those instructions instead of a button.

const DISMISS_KEY = 'silverlake:installBannerDismissedAt'
const DISMISS_DAYS = 30

export const installState = reactive({
  canPrompt: false,
  installed: false,
})

let deferredPrompt = null

export function isStandalone() {
  return window.matchMedia?.('(display-mode: standalone)').matches === true || window.navigator.standalone === true
}

export function isIos() {
  const ua = window.navigator.userAgent || ''
  if (/iphone|ipad|ipod/i.test(ua)) return true
  // iPadOS 13+ reports itself as a Mac; touch support is what gives it away.
  return /macintosh/i.test(ua) && (window.navigator.maxTouchPoints || 0) > 1
}

export function initInstallPrompt() {
  installState.installed = isStandalone()

  window.addEventListener('beforeinstallprompt', (event) => {
    // Stop the browser's own mini-infobar; our banner offers the same dialog on our terms.
    event.preventDefault()
    deferredPrompt = event
    installState.canPrompt = true
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    installState.canPrompt = false
    installState.installed = true
  })
}

// Must be called from a click handler - browsers refuse prompt() without a user gesture.
// Resolves to 'accepted', 'dismissed', or 'unavailable'.
export async function promptInstall() {
  if (!deferredPrompt) return 'unavailable'
  const event = deferredPrompt
  // The event is single-use either way, so forget it before awaiting the user's choice.
  deferredPrompt = null
  installState.canPrompt = false
  await event.prompt()
  const { outcome } = await event.userChoice
  return outcome
}

export function wasRecentlyDismissed(now = Date.now()) {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY))
    return Boolean(at) && now - at < DISMISS_DAYS * 24 * 60 * 60 * 1000
  } catch {
    return false
  }
}

export function rememberDismissal(now = Date.now()) {
  try {
    localStorage.setItem(DISMISS_KEY, String(now))
  } catch {
    // Private mode / blocked storage - the banner just comes back next visit.
  }
}
