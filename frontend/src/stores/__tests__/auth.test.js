import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/client', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

import apiClient from '../../api/client'
import { useAuthStore } from '../auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts logged out with no stored session', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
  })

  it('login() establishes a session immediately when 2FA is not required', async () => {
    apiClient.post.mockResolvedValue({
      data: { user: { id: 1, email: 'a@example.com' }, access: 'acc', refresh: 'ref' },
    })
    const auth = useAuthStore()

    await auth.login('a@example.com', 'pw')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.accessToken).toBe('acc')
    expect(localStorage.getItem('sl_access')).toBe('acc')
    expect(localStorage.getItem('sl_user')).toBe(JSON.stringify({ id: 1, email: 'a@example.com' }))
  })

  it('login() does not establish a session when two_factor_required is returned', async () => {
    apiClient.post.mockResolvedValue({ data: { two_factor_required: true, user_id: 42 } })
    const auth = useAuthStore()

    const result = await auth.login('staff@example.com', 'pw')

    expect(result.two_factor_required).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('sl_access')).toBeNull()
  })

  it('verifyTwoFactorLogin() establishes the session using the returned tokens', async () => {
    apiClient.post.mockResolvedValue({
      data: { user: { id: 9, email: 'staff@example.com' }, access: 'acc2', refresh: 'ref2' },
    })
    const auth = useAuthStore()

    await auth.verifyTwoFactorLogin(42, '123456')

    expect(apiClient.post).toHaveBeenCalledWith('/auth/2fa/verify/', { user_id: 42, code: '123456' })
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.accessToken).toBe('acc2')
  })

  it('logout() clears session state and localStorage even before the request resolves', async () => {
    apiClient.post.mockResolvedValue({ data: {} })
    const auth = useAuthStore()
    auth.setSession({ user: { id: 1 }, access: 'acc', refresh: 'ref' })

    await auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('sl_access')).toBeNull()
    expect(localStorage.getItem('sl_refresh')).toBeNull()
  })

  it('logout() does not call the API when there is no refresh token to revoke', async () => {
    const auth = useAuthStore()
    auth.user = { id: 1 }
    auth.accessToken = 'acc'
    auth.refreshToken = ''

    await auth.logout()

    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('logout() swallows a failed revoke request - local logout still happens', async () => {
    apiClient.post.mockRejectedValue(new Error('network error'))
    const auth = useAuthStore()
    auth.setSession({ user: { id: 1 }, access: 'acc', refresh: 'ref' })

    await expect(auth.logout()).resolves.toBeUndefined()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('startImpersonation() stashes the admin session and switches to the target user', async () => {
    apiClient.post.mockResolvedValue({
      data: { user: { id: 2, email: 'customer@example.com' }, access: 'target-acc', refresh: 'target-ref' },
    })
    const auth = useAuthStore()
    auth.setSession({ user: { id: 1, email: 'admin@example.com' }, access: 'admin-acc', refresh: 'admin-ref' })

    await auth.startImpersonation(2, '/admin/users')

    expect(auth.user).toEqual({ id: 2, email: 'customer@example.com' })
    expect(auth.accessToken).toBe('target-acc')
    expect(auth.impersonating.user).toEqual({ id: 1, email: 'admin@example.com' })
    expect(auth.impersonating.returnPath).toBe('/admin/users')
  })

  it('stopImpersonation() restores the stashed admin session and returns the saved path', async () => {
    apiClient.post.mockResolvedValue({
      data: { user: { id: 2 }, access: 'target-acc', refresh: 'target-ref' },
    })
    const auth = useAuthStore()
    auth.setSession({ user: { id: 1 }, access: 'admin-acc', refresh: 'admin-ref' })
    await auth.startImpersonation(2, '/admin/users')

    const returnPath = auth.stopImpersonation()

    expect(returnPath).toBe('/admin/users')
    expect(auth.user).toEqual({ id: 1 })
    expect(auth.accessToken).toBe('admin-acc')
    expect(auth.impersonating).toBeNull()
  })

  it('stopImpersonation() is a no-op when not currently impersonating', () => {
    const auth = useAuthStore()
    expect(auth.stopImpersonation()).toBeNull()
  })

  it('refreshProfile() does nothing when logged out', async () => {
    const auth = useAuthStore()
    await auth.refreshProfile()
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('refreshProfile() silently keeps the stale profile if the request fails', async () => {
    apiClient.get.mockRejectedValue(new Error('network error'))
    const auth = useAuthStore()
    auth.setSession({ user: { id: 1, email: 'old@example.com' }, access: 'acc', refresh: 'ref' })

    await expect(auth.refreshProfile()).resolves.toBeUndefined()
    expect(auth.user).toEqual({ id: 1, email: 'old@example.com' })
  })
})
