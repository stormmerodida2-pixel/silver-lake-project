import * as Sentry from '@sentry/vue'

const DSN = import.meta.env.VITE_SENTRY_DSN

// No-ops entirely (the SDK is never even initialized) when no DSN is configured - local dev and
// any deploy that hasn't set VITE_SENTRY_DSN stays untouched rather than reporting noise into
// someone else's Sentry project. Mirrors analytics.js's own "blank env var disables it" pattern.
export function initErrorTracking(app, router) {
  if (!DSN) return
  Sentry.init({
    app,
    dsn: DSN,
    integrations: [Sentry.browserTracingIntegration({ router })],
    environment: import.meta.env.MODE,
    // A modest sample of transactions for performance tracing, not every single page view -
    // errors themselves are always captured regardless of this.
    tracesSampleRate: 0.1,
  })
}
