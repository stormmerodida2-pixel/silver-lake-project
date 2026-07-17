import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('sl_user') || 'null'),
    accessToken: localStorage.getItem('sl_access') || '',
    refreshToken: localStorage.getItem('sl_refresh') || '',
    // Set only while a superadmin is impersonating someone else - holds their own real session
    // (to restore on stop) plus the admin page they were on, so "Stop impersonating" can return
    // them exactly where they started rather than dumping them somewhere generic.
    impersonating: JSON.parse(localStorage.getItem('sl_impersonating') || 'null'),
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
    async register({ firstName, lastName, email, phoneNumber, password }) {
      // No session returned here - the account is inactive until the user clicks the activation email link.
      const { data } = await apiClient.post('/auth/register/', {
        first_name: firstName,
        last_name: lastName,
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
    async refreshProfile() {
      // auth.user is only ever set at login and cached in localStorage - if a role changes
      // server-side afterward (e.g. a driver application gets approved), this re-syncs it
      // without forcing a fresh login. Fails silently - a stale profile isn't worth breaking
      // the page over.
      if (!this.isAuthenticated) return
      try {
        const { data } = await apiClient.get('/auth/me/')
        this.user = data
        localStorage.setItem('sl_user', JSON.stringify(data))
      } catch (err) {
        // ignore - keep whatever profile we already have
      }
    },
    async startImpersonation(userId, returnPath) {
      // Stash the admin's own real session first - startImpersonation replaces
      // user/accessToken/refreshToken with the target's below, and this is the only copy of
      // the admin's own tokens once that happens.
      const adminSession = {
        user: this.user,
        accessToken: this.accessToken,
        refreshToken: this.refreshToken,
        returnPath,
      }
      const { data } = await apiClient.post(`/admin/users/${userId}/impersonate/`)
      this.impersonating = adminSession
      localStorage.setItem('sl_impersonating', JSON.stringify(adminSession))
      this.setSession(data)
    },
    stopImpersonation() {
      if (!this.impersonating) return null
      const { user, accessToken, refreshToken, returnPath } = this.impersonating
      this.setSession({ user, access: accessToken, refresh: refreshToken })
      this.impersonating = null
      localStorage.removeItem('sl_impersonating')
      return returnPath
    },
    async logout() {
      // Capture both tokens before clearing local state - the request interceptor reads the
      // access token straight from localStorage, which is about to be wiped, so this request
      // needs its own explicit Authorization header rather than relying on that.
      const refresh = this.refreshToken
      const access = this.accessToken

      // Clear local state up front (synchronously, before the request below) so the UI updates
      // instantly regardless of whether the caller awaits this - the network call to actually
      // revoke the token server-side is best-effort from here on.
      this.user = null
      this.accessToken = ''
      this.refreshToken = ''
      localStorage.removeItem('sl_user')
      localStorage.removeItem('sl_access')
      localStorage.removeItem('sl_refresh')
      // Logging out while impersonating means "end everything", not "return to my admin
      // session" - otherwise the stashed admin session would linger indefinitely with no way
      // back to it, since the banner that offers Stop Impersonating is now gone too.
      this.impersonating = null
      localStorage.removeItem('sl_impersonating')

      if (refresh) {
        try {
          await apiClient.post(
            '/auth/logout/',
            { refresh },
            { headers: { Authorization: `Bearer ${access}` } },
          )
        } catch (err) {
          // Token already expired/invalid, or a network hiccup - local logout already happened.
        }
      }
    },
  },
})
