import axios from 'axios'

import { reportClientError } from '../utils/clientErrorReporting'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('sl_access')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Silent token refresh on 401 — retries the original request once with a fresh token.
let isRefreshing = false
let failedQueue = []

function processQueue(error, token = null) {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error)
    else prom.resolve(token)
  })
  failedQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const status = error.response?.status
    const url = original?.url || ''
    const isAuthRequest = url.includes('auth/login') || url.includes('auth/register') || url.includes('auth/activate') || url.includes('token/refresh')

    // A 400 ("email already taken", wrong password) is normal, expected user-input feedback -
    // not a bug. But a 500 or a request that never got a response at all (network drop, CORS,
    // timeout, DNS failure) during something like signup is a real problem the visitor hit,
    // even though the calling component catches it and shows a friendly message instead of
    // letting it crash - so window.onerror/unhandledrejection alone would never see it. Skip
    // the report endpoint itself and deliberate cancellations to avoid noise/loops.
    const isReportEndpoint = url.includes('report-client-error')
    const isCancelled = error.code === 'ERR_CANCELED' || axios.isCancel(error)
    if (!isReportEndpoint && !isCancelled && (status >= 500 || !error.response)) {
      const method = (original?.method || '?').toUpperCase()
      reportClientError(`API error: ${method} ${url} - ${status || error.message || 'network error'}`, '')
    }

    if (status === 401 && !original._retry && !isAuthRequest) {
      const refresh = localStorage.getItem('sl_refresh')
      if (!refresh) {
        // No refresh token — clear state and go home, same as an explicit logout
        localStorage.removeItem('sl_user')
        localStorage.removeItem('sl_access')
        localStorage.removeItem('sl_refresh')
        window.location.href = '/'
        return Promise.reject(error)
      }

      if (isRefreshing) {
        // Queue concurrent requests until the refresh resolves
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return apiClient(original)
        })
      }

      original._retry = true
      isRefreshing = true

      try {
        // Goes through apiClient (not a raw axios.post) so it reuses the same baseURL joining
        // axios already does correctly for every other request - hand-concatenating
        // VITE_API_BASE_URL + 'token/refresh/' silently breaks whenever the env var lacks a
        // trailing slash (it does in both this repo's dev .env and the CI-built production
        // one), producing a malformed .../apitoken/refresh/ URL that 404s. isAuthRequest above
        // already exempts this call's own 401s from re-triggering refresh, so reusing apiClient
        // here can't cause a refresh loop.
        const { data } = await apiClient.post('token/refresh/', { refresh })
        const newAccess = data.access
        localStorage.setItem('sl_access', newAccess)
        processQueue(null, newAccess)
        original.headers.Authorization = `Bearer ${newAccess}`
        return apiClient(original)
      } catch (refreshError) {
        processQueue(refreshError)
        localStorage.removeItem('sl_user')
        localStorage.removeItem('sl_access')
        localStorage.removeItem('sl_refresh')
        window.location.href = '/'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
