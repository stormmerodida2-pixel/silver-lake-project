import { expect, test } from '@playwright/test'

import { E2E_VEHICLE_NAME } from './helpers'

test.describe('Public site smoke test', () => {
  test('home page loads and the nav links to Fleet', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/SilverLake/)
    await page.locator('header').getByRole('link', { name: 'Fleet', exact: true }).click()
    await expect(page).toHaveURL(/\/fleet/)
  })

  test('the seeded vehicle appears on the fleet page', async ({ page }) => {
    await page.goto('/fleet')
    await expect(page.getByText(E2E_VEHICLE_NAME)).toBeVisible()
  })

  // Regression coverage for the mobile header fix - bell + hamburger grouped together,
  // clicking the hamburger reveals the mobile nav panel, clicking it again closes it.
  test('mobile hamburger menu opens and closes', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')

    const menuButton = page.getByRole('button', { name: 'Toggle menu' })
    const panel = page.getByTestId('mobile-nav-panel')

    await expect(menuButton).toHaveAttribute('aria-expanded', 'false')
    await expect(panel).not.toBeAttached()

    await menuButton.click()
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true')
    await expect(panel).toBeVisible()
    await expect(panel.getByRole('link', { name: 'Fleet', exact: true })).toBeVisible()

    await menuButton.click()
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false')
    await expect(panel).not.toBeAttached()
  })
})
