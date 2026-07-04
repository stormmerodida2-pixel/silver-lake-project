import axios from 'axios'

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

    if (status === 401 && !original._retry) {
      const refresh = localStorage.getItem('sl_refresh')
      if (!refresh) {
        // No refresh token — clear state and go to login
        localStorage.removeItem('sl_access')
        localStorage.removeItem('sl_refresh')
        window.location.href = '/login'
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
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL}token/refresh/`,
          { refresh }
        )
        const newAccess = data.access
        localStorage.setItem('sl_access', newAccess)
        processQueue(null, newAccess)
        original.headers.Authorization = `Bearer ${newAccess}`
        return apiClient(original)
      } catch (refreshError) {
        processQueue(refreshError)
        localStorage.removeItem('sl_access')
        localStorage.removeItem('sl_refresh')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
