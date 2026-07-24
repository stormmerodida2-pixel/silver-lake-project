import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

async function freshModule() {
  vi.resetModules()
  document.head.innerHTML = ''
  delete window.gtag
  delete window.dataLayer
  return import('../analytics')
}

describe('analytics', () => {
  beforeEach(() => {
    document.head.innerHTML = ''
    delete window.gtag
    delete window.dataLayer
  })

  afterEach(() => vi.unstubAllEnvs())

  describe('initAnalytics', () => {
    it('never injects the gtag script when VITE_GA_MEASUREMENT_ID is unset', async () => {
      vi.stubEnv('VITE_GA_MEASUREMENT_ID', '')
      const { initAnalytics } = await freshModule()

      initAnalytics()

      expect(document.head.querySelector('script[src*="googletagmanager"]')).toBeNull()
      expect(window.gtag).toBeUndefined()
    })

    it('injects the gtag script and configures it once a measurement ID is set', async () => {
      vi.stubEnv('VITE_GA_MEASUREMENT_ID', 'G-TESTID123')
      const { initAnalytics } = await freshModule()

      initAnalytics()

      const script = document.head.querySelector('script[src*="googletagmanager"]')
      expect(script).not.toBeNull()
      expect(script.src).toContain('G-TESTID123')
      expect(typeof window.gtag).toBe('function')
    })

    it('only injects the script once even if called multiple times', async () => {
      vi.stubEnv('VITE_GA_MEASUREMENT_ID', 'G-TESTID123')
      const { initAnalytics } = await freshModule()

      initAnalytics()
      initAnalytics()

      expect(document.head.querySelectorAll('script[src*="googletagmanager"]').length).toBe(1)
    })
  })

  describe('trackPageView / trackEvent', () => {
    it('are silent no-ops when gtag was never initialized', async () => {
      vi.stubEnv('VITE_GA_MEASUREMENT_ID', '')
      const { initAnalytics, trackPageView, trackEvent } = await freshModule()
      initAnalytics()

      expect(() => trackPageView('/fleet', 'Fleet')).not.toThrow()
      expect(() => trackEvent('select_item', { item_id: '1' })).not.toThrow()
    })

    it('forward to window.gtag once analytics is active', async () => {
      vi.stubEnv('VITE_GA_MEASUREMENT_ID', 'G-TESTID123')
      const { initAnalytics, trackPageView, trackEvent } = await freshModule()
      initAnalytics()
      const calls = []
      window.gtag = (...args) => calls.push(args)

      trackPageView('/fleet', 'Fleet | SilverLake')
      trackEvent('select_item', { item_id: '1' })

      expect(calls).toContainEqual(['event', 'page_view', { page_path: '/fleet', page_title: 'Fleet | SilverLake' }])
      expect(calls).toContainEqual(['event', 'select_item', { item_id: '1' }])
    })
  })
})
