import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MockAdapter from 'axios-mock-adapter'

vi.mock('../../utils/clientErrorReporting', () => ({
  reportClientError: vi.fn(),
}))

// Each test gets a fresh module instance - the interceptor keeps module-level state
// (isRefreshing/failedQueue) that must not leak between tests.
async function freshClient() {
  vi.resetModules()
  const clientModule = await import('../client')
  const { reportClientError } = await import('../../utils/clientErrorReporting')
  return { apiClient: clientModule.default, reportClientError }
}

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('attaches an Authorization header when an access token is stored', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_access', 'token-abc')
    const mock = new MockAdapter(apiClient)
    mock.onGet('/vehicles/').reply((config) => {
      expect(config.headers.Authorization).toBe('Bearer token-abc')
      return [200, []]
    })
    await apiClient.get('/vehicles/')
    mock.restore()
  })

  it('sends no Authorization header when logged out', async () => {
    const { apiClient } = await freshClient()
    const mock = new MockAdapter(apiClient)
    mock.onGet('/vehicles/').reply((config) => {
      expect(config.headers.Authorization).toBeUndefined()
      return [200, []]
    })
    await apiClient.get('/vehicles/')
    mock.restore()
  })
})

describe('apiClient 401 refresh-and-retry', () => {
  let originalLocation

  beforeEach(() => {
    localStorage.clear()
    originalLocation = window.location
    delete window.location
    window.location = { ...originalLocation, href: '' }
  })

  afterEach(() => {
    window.location = originalLocation
  })

  it('refreshes the access token once and retries the original request', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_access', 'stale-token')
    localStorage.setItem('sl_refresh', 'refresh-token')
    const mock = new MockAdapter(apiClient)

    let vehiclesCallCount = 0
    mock.onGet('/vehicles/').reply((config) => {
      vehiclesCallCount += 1
      if (config.headers.Authorization === 'Bearer stale-token') return [401, { detail: 'expired' }]
      if (config.headers.Authorization === 'Bearer fresh-token') return [200, [{ id: 1 }]]
      return [401]
    })
    mock.onPost('token/refresh/').reply(200, { access: 'fresh-token' })

    const { data } = await apiClient.get('/vehicles/')

    expect(data).toEqual([{ id: 1 }])
    expect(vehiclesCallCount).toBe(2)
    expect(localStorage.getItem('sl_access')).toBe('fresh-token')
    mock.restore()
  })

  it('queues concurrent requests during an in-flight refresh and retries all of them once', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_access', 'stale-token')
    localStorage.setItem('sl_refresh', 'refresh-token')
    const mock = new MockAdapter(apiClient)

    let refreshCallCount = 0
    mock.onPost('token/refresh/').reply(() => {
      refreshCallCount += 1
      return [200, { access: 'fresh-token' }]
    })
    mock
      .onGet('/vehicles/')
      .reply((config) => (config.headers.Authorization === 'Bearer fresh-token' ? [200, ['vehicles']] : [401]))
    mock
      .onGet('/reviews/')
      .reply((config) => (config.headers.Authorization === 'Bearer fresh-token' ? [200, ['reviews']] : [401]))

    const [vehicles, reviews] = await Promise.all([apiClient.get('/vehicles/'), apiClient.get('/reviews/')])

    expect(vehicles.data).toEqual(['vehicles'])
    expect(reviews.data).toEqual(['reviews'])
    // Only one real refresh call, even though two requests hit a 401 concurrently.
    expect(refreshCallCount).toBe(1)
    mock.restore()
  })

  it('clears the session and redirects home when the refresh call itself fails', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_user', '{"id":1}')
    localStorage.setItem('sl_access', 'stale-token')
    localStorage.setItem('sl_refresh', 'expired-refresh-token')
    const mock = new MockAdapter(apiClient)
    mock.onGet('/vehicles/').reply(401)
    mock.onPost('token/refresh/').reply(401, { detail: 'refresh token expired' })

    await expect(apiClient.get('/vehicles/')).rejects.toBeTruthy()

    expect(localStorage.getItem('sl_user')).toBeNull()
    expect(localStorage.getItem('sl_access')).toBeNull()
    expect(localStorage.getItem('sl_refresh')).toBeNull()
    expect(window.location.href).toBe('/')
    mock.restore()
  })

  it('clears the session and redirects home immediately when there is no refresh token at all', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_access', 'stale-token')
    const mock = new MockAdapter(apiClient)
    let refreshCalled = false
    mock.onPost('token/refresh/').reply(() => {
      refreshCalled = true
      return [200, { access: 'fresh-token' }]
    })
    mock.onGet('/vehicles/').reply(401)

    await expect(apiClient.get('/vehicles/')).rejects.toBeTruthy()

    expect(refreshCalled).toBe(false)
    expect(window.location.href).toBe('/')
    mock.restore()
  })

  it('does not attempt a refresh for a 401 on the login endpoint itself', async () => {
    const { apiClient } = await freshClient()
    localStorage.setItem('sl_refresh', 'refresh-token')
    const mock = new MockAdapter(apiClient)
    let refreshCalled = false
    mock.onPost('token/refresh/').reply(() => {
      refreshCalled = true
      return [200, { access: 'fresh-token' }]
    })
    mock.onPost('auth/login/').reply(401, { detail: 'Invalid credentials' })

    await expect(apiClient.post('auth/login/', {})).rejects.toBeTruthy()

    expect(refreshCalled).toBe(false)
    mock.restore()
  })
})

describe('apiClient client-error reporting', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('reports a 500 response', async () => {
    const { apiClient, reportClientError } = await freshClient()
    const mock = new MockAdapter(apiClient)
    mock.onGet('/vehicles/').reply(500)

    await expect(apiClient.get('/vehicles/')).rejects.toBeTruthy()

    expect(reportClientError).toHaveBeenCalledTimes(1)
    expect(reportClientError.mock.calls[0][0]).toContain('500')
    mock.restore()
  })

  it('does not report a plain 400 validation error', async () => {
    const { apiClient, reportClientError } = await freshClient()
    const mock = new MockAdapter(apiClient)
    mock.onPost('auth/register/').reply(400, { email: ['Already registered'] })

    await expect(apiClient.post('auth/register/', {})).rejects.toBeTruthy()

    expect(reportClientError).not.toHaveBeenCalled()
    mock.restore()
  })

  it('does not report a failure of the error-reporting endpoint itself', async () => {
    const { apiClient, reportClientError } = await freshClient()
    const mock = new MockAdapter(apiClient)
    mock.onPost('report-client-error/').reply(500)

    await expect(apiClient.post('report-client-error/', {})).rejects.toBeTruthy()

    expect(reportClientError).not.toHaveBeenCalled()
    mock.restore()
  })
})
