import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('sl_user') || 'null'),
    accessToken: localStorage.getItem('sl_access') || '',
    refreshToken: localStorage.getItem('sl_refresh') || '',
  }),
  getters: {
    isAuthenticated: (state) => !!state.accessToken,
  },
  actions: {
    setSession({ user, access, refresh }) {
      this.user = user
      this.accessToken = access
      this.refreshToken = refresh
      localStorage.setItem('sl_user', JSON.stringify(user))
      localStorage.setItem('sl_access', access)
      localStorage.setItem('sl_refresh', refresh)
    },
    async login(email, password) {
      const { data } = await apiClient.post('/auth/login/', { username: email, password })
      this.setSession(data)
    },
    async register({ fullName, email, phoneNumber, password }) {
      // No session returned here - the account is inactive until the user clicks the activation email link.
      const { data } = await apiClient.post('/auth/register/', {
        full_name: fullName,
        email,
        phone_number: phoneNumber,
        password,
      })
      return data
    },
    async activateAccount(uid, token) {
      const { data } = await apiClient.post(`/auth/activate/${uid}/${token}/`)
      return data
    },
    async requestPasswordReset(email) {
      const { data } = await apiClient.post('/auth/password-reset/', { email })
      return data
    },
    async confirmPasswordReset(uid, token, newPassword) {
      const { data } = await apiClient.post('/auth/password-reset/confirm/', {
        uid,
        token,
        new_password: newPassword,
      })
      return data
    },
    async changePassword(oldPassword, newPassword) {
      const { data } = await apiClient.post('/auth/change-password/', {
        old_password: oldPassword,
        new_password: newPassword,
      })
      return data
    },
    logout() {
      this.user = null
      this.accessToken = ''
      this.refreshToken = ''
      localStorage.removeItem('sl_user')
      localStorage.removeItem('sl_access')
      localStorage.removeItem('sl_refresh')
    },
  },
})
