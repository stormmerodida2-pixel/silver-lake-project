import { expect, test } from '@playwright/test'

import { E2E_ADMIN_EMAIL, E2E_PASSWORD, login } from './helpers'

test.describe('Admin dashboard', () => {
  test('superadmin can log in and reach the dashboard', async ({ page }) => {
    await login(page, E2E_ADMIN_EMAIL, E2E_PASSWORD)
    await expect(page).toHaveURL('/admin')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })

  // Regression coverage for the searchable/clickable vehicle list added to the Fleet Map.
  test('Fleet Map loads with the vehicle search list', async ({ page }) => {
    await login(page, E2E_ADMIN_EMAIL, E2E_PASSWORD)
    await page.goto('/admin/fleet-map')
    await expect(page.getByRole('heading', { name: 'Fleet Map' })).toBeVisible()
    await expect(page.getByPlaceholder('Search by vehicle or driver...')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Refresh & recenter' })).toBeVisible()
  })

  test('System Health page loads', async ({ page }) => {
    await login(page, E2E_ADMIN_EMAIL, E2E_PASSWORD)
    await page.goto('/admin/health')
    await expect(page.getByRole('heading', { name: 'System Health' })).toBeVisible()
  })
})
