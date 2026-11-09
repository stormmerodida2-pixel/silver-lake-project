import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  initInstallPrompt,
  installState,
  isIos,
  promptInstall,
  rememberDismissal,
  wasRecentlyDismissed,
} from '../pwaInstall'

function fakeInstallEvent(outcome = 'accepted') {
  const event = new Event('beforeinstallprompt', { cancelable: true })
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome })
  return event
}

function setUserAgent(ua, maxTouchPoints = 0) {
  Object.defineProperty(window.navigator, 'userAgent', { value: ua, configurable: true })
  Object.defineProperty(window.navigator, 'maxTouchPoints', { value: maxTouchPoints, configurable: true })
}

describe('pwaInstall', () => {
  beforeEach(() => {
    localStorage.clear()
    installState.canPrompt = false
    installState.installed = false
  })

  it('holds the browser install event and suppresses the default mini-infobar', async () => {
    initInstallPrompt()
    const event = fakeInstallEvent()
    window.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
    expect(installState.canPrompt).toBe(true)

    await expect(promptInstall()).resolves.toBe('accepted')
    expect(event.prompt).toHaveBeenCalledOnce()
    // The event is single-use.
    expect(installState.canPrompt).toBe(false)
    await expect(promptInstall()).resolves.toBe('unavailable')
  })

  it('reports a declined install as dismissed', async () => {
    initInstallPrompt()
    window.dispatchEvent(fakeInstallEvent('dismissed'))
    await expect(promptInstall()).resolves.toBe('dismissed')
  })

  it('marks the app installed once the browser says so', () => {
    initInstallPrompt()
    window.dispatchEvent(fakeInstallEvent())
    window.dispatchEvent(new Event('appinstalled'))
    expect(installState.installed).toBe(true)
    expect(installState.canPrompt).toBe(false)
  })

  it('remembers a dismissal for 30 days', () => {
    const now = Date.UTC(2026, 10, 9)
    const day = 24 * 60 * 60 * 1000
    expect(wasRecentlyDismissed(now)).toBe(false)
    rememberDismissal(now)
    expect(wasRecentlyDismissed(now + 29 * day)).toBe(true)
    expect(wasRecentlyDismissed(now + 31 * day)).toBe(false)
  })

  it('detects iPhones and iPads (including iPadOS posing as a Mac)', () => {
    setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15')
    expect(isIos()).toBe(true)
    setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15', 5)
    expect(isIos()).toBe(true)
    setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15', 0)
    expect(isIos()).toBe(false)
    setUserAgent('Mozilla/5.0 (Linux; Android 14; SM-A145F) AppleWebKit/537.36 Chrome/130.0 Mobile')
    expect(isIos()).toBe(false)
  })
})
