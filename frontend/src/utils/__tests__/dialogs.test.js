import { beforeEach, describe, expect, it, vi } from 'vitest'

// toastFire is the mixin instance's own fire, kept distinct from Swal.fire itself so
// showToast's assertions can't accidentally pass by checking the wrong mock.
const { toastFire, mixinFn } = vi.hoisted(() => {
  const toastFire = vi.fn()
  return { toastFire, mixinFn: vi.fn(() => ({ fire: toastFire })) }
})

vi.mock('sweetalert2', () => ({
  default: { fire: vi.fn(), mixin: mixinFn, stopTimer: vi.fn(), resumeTimer: vi.fn() },
}))

import Swal from 'sweetalert2'
import { confirmDialog, promptDialog, showToast } from '../dialogs'

describe('confirmDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('resolves true when confirmed', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: true })
    await expect(confirmDialog('Are you sure?')).resolves.toBe(true)
  })

  it('resolves false when cancelled', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: false })
    await expect(confirmDialog('Are you sure?')).resolves.toBe(false)
  })

  it('uses a red confirm button for danger actions, gold otherwise', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: true })

    await confirmDialog('Delete this?', { danger: true })
    expect(Swal.fire.mock.calls[0][0].confirmButtonColor).toBe('#dc2626')

    await confirmDialog('Continue?')
    expect(Swal.fire.mock.calls[1][0].confirmButtonColor).toBe('#c9a227')
  })
})

describe('promptDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns the entered value when confirmed', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: true, value: 'MPESA1234' })
    await expect(promptDialog('Enter reference:')).resolves.toBe('MPESA1234')
  })

  it('returns null when cancelled, even if a value was typed', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: false, value: 'ignored' })
    await expect(promptDialog('Enter reference:')).resolves.toBeNull()
  })

  it('passes through the requested input type (e.g. password)', async () => {
    Swal.fire.mockResolvedValue({ isConfirmed: true, value: 'secret' })
    await promptDialog('Confirm your password', { inputType: 'password' })
    expect(Swal.fire.mock.calls[0][0].input).toBe('password')
  })
})

describe('showToast', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fires a success toast by default', () => {
    showToast('Added to favorites')
    expect(toastFire).toHaveBeenCalledWith({ icon: 'success', title: 'Added to favorites' })
  })

  it('supports overriding the icon', () => {
    showToast('Could not update favorites', { icon: 'error' })
    expect(toastFire).toHaveBeenCalledWith({ icon: 'error', title: 'Could not update favorites' })
  })
})
