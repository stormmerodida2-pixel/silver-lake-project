import { expect, test } from '@playwright/test'

import { E2E_CUSTOMER_EMAIL, E2E_PASSWORD, E2E_VEHICLE_NAME, login } from './helpers'

test('a customer can apply their referral credit toward a booking', async ({ page }) => {
  await login(page, E2E_CUSTOMER_EMAIL, E2E_PASSWORD)

  // Profile shows the referral code and available credit (seeded by seed_e2e_data).
  await page.goto('/account/profile')
  await expect(page.getByText('Available Credit')).toBeVisible()
  const creditCode = await page.locator('span.font-mono').innerText()
  expect(creditCode).toMatch(/^[A-Z0-9]{8}$/)

  // Book the seeded vehicle, using a random future date window to avoid clashing with a
  // leftover booking from another spec/run on the same vehicle.
  await page.goto('/fleet')
  await page.getByText(E2E_VEHICLE_NAME).click()
  await page.getByRole('link', { name: 'Book with Driver' }).click()

  const offset = 20 + Math.floor(Math.random() * 300)
  const today = new Date()
  const start = new Date(today)
  start.setDate(start.getDate() + offset)
  const end = new Date(today)
  end.setDate(end.getDate() + offset + 2)
  const toDateInput = (d) => d.toISOString().split('T')[0]

  await page.locator('label:has-text("Start date") + input').fill(toDateInput(start))
  await page.locator('label:has-text("End date") + input').fill(toDateInput(end))
  await page.locator('label:has-text("Pickup location") + input').fill('Kisumu Airport')
  await page.getByRole('button', { name: 'Confirm Booking' }).click()
  await expect(page.getByRole('heading', { name: 'Booking Received' })).toBeVisible()

  const payInFullButton = page.getByRole('button').filter({ hasText: 'Pay in Full' })
  const payInFullBefore = await payInFullButton.innerText()

  await page.getByRole('button', { name: 'Apply Credit' }).click()
  // The whole banner disappears once the customer's credit balance hits zero - waiting on the
  // button's own text is unreliable, since it reads "Applying..." while the request is still
  // in flight (a different accessible name, so a name-scoped locator would stop matching it
  // immediately without actually waiting for completion).
  await expect(page.getByText('in referral credit available')).not.toBeVisible()

  const payInFullAfter = await payInFullButton.innerText()
  expect(payInFullAfter).not.toEqual(payInFullBefore)
})
