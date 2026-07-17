const MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID

let initialized = false

// No-ops entirely (never loads Google's script) when no ID is configured - local dev and any
// deploy that hasn't set VITE_GA_MEASUREMENT_ID stay untracked rather than polluting real data.
export function initAnalytics() {
  if (!MEASUREMENT_ID || initialized) return
  initialized = true

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`
  document.head.appendChild(script)

  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag() { window.dataLayer.push(arguments) }
  window.gtag('js', new Date())
  // send_page_view disabled - gtag's automatic one only fires for the initial hard load, not
  // client-side route changes, so the router's afterEach hook sends page_view itself instead.
  window.gtag('config', MEASUREMENT_ID, { send_page_view: false })
}

export function trackPageView(path, title) {
  if (typeof window.gtag !== 'function') return
  window.gtag('event', 'page_view', { page_path: path, page_title: title })
}

// Thin wrapper so call sites never need to guard on gtag existing themselves.
export function trackEvent(name, params = {}) {
  if (typeof window.gtag !== 'function') return
  window.gtag('event', name, params)
}
