import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@sentry/vue', () => ({
  init: vi.fn(),
  browserTracingIntegration: vi.fn(() => ({})),
}))

async function freshModule() {
  vi.resetModules()
  const Sentry = await import('@sentry/vue')
  const { initErrorTracking } = await import('../errorTracking')
  return { Sentry, initErrorTracking }
}

describe('initErrorTracking', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.unstubAllEnvs())

  it('never calls Sentry.init when VITE_SENTRY_DSN is unset', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    const { Sentry, initErrorTracking } = await freshModule()

    initErrorTracking({}, {})

    expect(Sentry.init).not.toHaveBeenCalled()
  })

  it('initializes Sentry with the configured DSN when set', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://examplekey@o0.ingest.sentry.io/1')
    const { Sentry, initErrorTracking } = await freshModule()
    const app = { name: 'fake-app' }
    const router = { name: 'fake-router' }

    initErrorTracking(app, router)

    expect(Sentry.init).toHaveBeenCalledTimes(1)
    const options = Sentry.init.mock.calls[0][0]
    expect(options.dsn).toBe('https://examplekey@o0.ingest.sentry.io/1')
    expect(options.app).toBe(app)
  })
})
