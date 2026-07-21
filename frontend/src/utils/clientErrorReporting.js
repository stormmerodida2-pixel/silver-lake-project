// The no-Sentry-required side of frontend error visibility - core.views.ReportClientErrorView
// logs every report (always visible via `docker logs`) and emails admins too if ADMIN_ERROR_EMAIL
// is configured, the same way an unhandled backend exception already does. Always active,
// independent of errorTracking.js/Sentry - this runs whether or not a Sentry DSN is ever set.
const REPORT_URL = `${(import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')}/report-client-error/`

// De-dupes the same error within a short window - a bad render loop or a spammy third-party
// script can otherwise fire the same error dozens of times a second, which would otherwise mean
// dozens of admin emails for what's really one incident.
const recentErrors = new Map()
const DEDUPE_WINDOW_MS = 60000

export function reportClientError(message, stack) {
  const safeMessage = message || '(no message)'
  const safeStack = stack || ''
  const key = `${safeMessage}::${safeStack.slice(0, 200)}`
  const now = Date.now()
  const lastSeen = recentErrors.get(key)
  if (lastSeen && now - lastSeen < DEDUPE_WINDOW_MS) return
  recentErrors.set(key, now)

  // fetch + keepalive (not the axios apiClient) - keepalive lets the request survive the page
  // unloading, which matters since plenty of real crashes happen right as someone navigates
  // away. Deliberately fire-and-forget: a failure to report an error must never itself surface
  // as another one.
  fetch(REPORT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: safeMessage, stack: safeStack, url: window.location.href }),
    keepalive: true,
  }).catch(() => {})
}

export function initClientErrorReporting() {
  window.addEventListener('error', (event) => {
    reportClientError(event.message, event.error?.stack)
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    reportClientError(reason?.message || String(reason), reason?.stack)
  })
}
