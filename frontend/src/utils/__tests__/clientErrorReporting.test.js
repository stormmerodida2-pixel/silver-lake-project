import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

async function freshModule() {
  vi.resetModules()
  return import('../clientErrorReporting')
}

describe('reportClientError', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    global.fetch = vi.fn().mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('POSTs the error to the report endpoint with keepalive set', async () => {
    const { reportClientError } = await freshModule()

    reportClientError('Signup failed unexpectedly', 'Error: boom\n  at x.js:1:1')

    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toContain('/report-client-error/')
    expect(options.keepalive).toBe(true)
    const body = JSON.parse(options.body)
    expect(body.message).toBe('Signup failed unexpectedly')
    expect(body.stack).toContain('boom')
  })

  it('de-dupes the identical error within the dedupe window', async () => {
    const { reportClientError } = await freshModule()

    reportClientError('Boom', 'stack-a')
    reportClientError('Boom', 'stack-a')
    reportClientError('Boom', 'stack-a')

    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('reports the same message again once the dedupe window has passed', async () => {
    const { reportClientError } = await freshModule()

    reportClientError('Boom', 'stack-a')
    vi.advanceTimersByTime(60001)
    reportClientError('Boom', 'stack-a')

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('treats a different stack for the same message as a distinct error', async () => {
    const { reportClientError } = await freshModule()

    reportClientError('Boom', 'stack-a')
    reportClientError('Boom', 'stack-b')

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('never throws even if the report request itself fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network down'))
    const { reportClientError } = await freshModule()

    expect(() => reportClientError('Boom', '')).not.toThrow()
  })

  it('falls back to placeholder text for a blank message', async () => {
    const { reportClientError } = await freshModule()

    reportClientError('', '')

    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.message).toBe('(no message)')
  })
})

describe('initClientErrorReporting', () => {
  // Captures the handlers passed to addEventListener instead of dispatching real window events -
  // initClientErrorReporting() attaches its listeners with addEventListener directly, so a real
  // dispatch would keep stacking a new listener from every test in this file (they're never
  // torn down), double-firing later tests. Invoking the captured handler directly sidesteps that.
  let listeners

  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({})
    listeners = {}
    vi.spyOn(window, 'addEventListener').mockImplementation((type, handler) => {
      listeners[type] = handler
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('reports an uncaught window error', async () => {
    const { initClientErrorReporting } = await freshModule()
    initClientErrorReporting()

    listeners.error({ message: 'Uncaught TypeError', error: new Error('Uncaught TypeError') })

    expect(fetch).toHaveBeenCalledTimes(1)
    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.message).toBe('Uncaught TypeError')
  })

  it('reports an unhandled promise rejection', async () => {
    const { initClientErrorReporting } = await freshModule()
    initClientErrorReporting()

    listeners.unhandledrejection({ reason: new Error('Rejected for real') })

    expect(fetch).toHaveBeenCalledTimes(1)
    const body = JSON.parse(fetch.mock.calls[0][1].body)
    expect(body.message).toBe('Rejected for real')
  })
})
