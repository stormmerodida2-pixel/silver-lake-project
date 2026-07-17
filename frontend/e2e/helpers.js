// Fixed credentials created by `manage.py seed_e2e_data` (core/management/commands/seed_e2e_data.py).
// That command refuses to run outside DEBUG, so these are never valid against a real database.
export const E2E_CUSTOMER_EMAIL = 'e2e.customer@example.com'
export const E2E_ADMIN_EMAIL = 'e2e.admin@example.com'
export const E2E_PASSWORD = 'E2eTest123!'
export const E2E_VEHICLE_NAME = 'E2E Test Vehicle'

export async function login(page, email, password) {
  await page.goto('/login')
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Log In' }).click()
  // LoginView's submit() awaits the login API call before redirecting - without waiting here,
  // a caller that immediately does page.goto() next can race ahead of the auth token actually
  // being stored, landing back on /login via the router's auth guard.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
}
