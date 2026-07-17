import { expect, test } from '@playwright/test'

import { E2E_CUSTOMER_EMAIL, E2E_PASSWORD, login } from './helpers'

test.describe('Customer login', () => {
  test('logs in with valid credentials and can log out', async ({ page }) => {
    await login(page, E2E_CUSTOMER_EMAIL, E2E_PASSWORD)
    await expect(page).toHaveURL('/')
    await expect(page.getByText('Hi, E2E')).toBeVisible()

    // Logout goes through a SweetAlert2 confirm dialog, not the native confirm() - see
    // frontend/src/utils/dialogs.js's confirmDialog().
    await page.locator('header').getByRole('button', { name: 'Log Out' }).click()
    await page.getByRole('button', { name: 'Yes' }).click()
    await expect(page.locator('header').getByRole('link', { name: 'Log In', exact: true })).toBeVisible()
  })

  test('shows an error for an invalid password', async ({ page }) => {
    // Doesn't use the login() helper - it waits for a successful redirect away from /login,
    // which never happens here.
    await page.goto('/login')
    await page.locator('input[type="email"]').fill(E2E_CUSTOMER_EMAIL)
    await page.locator('input[type="password"]').fill('wrong-password')
    await page.getByRole('button', { name: 'Log In' }).click()

    // The backend's own SimpleJWT error message, surfaced verbatim by LoginView's error
    // fallback chain (err.response?.data?.detail || '...').
    await expect(page.getByText(/no active account found/i)).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
  })
})
