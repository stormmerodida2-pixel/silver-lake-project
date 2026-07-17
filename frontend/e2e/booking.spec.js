import { expect, test } from '@playwright/test'

import { E2E_CUSTOMER_EMAIL, E2E_PASSWORD, E2E_VEHICLE_NAME, login } from './helpers'

function futureDateString(daysFromNow) {
  const date = new Date()
  date.setDate(date.getDate() + daysFromNow)
  return date.toISOString().split('T')[0]
}

test('a logged-in customer can book the seeded vehicle, see it in My Bookings, and cancel it', async ({ page }) => {
  await login(page, E2E_CUSTOMER_EMAIL, E2E_PASSWORD)

  await page.goto('/fleet')
  await page.getByText(E2E_VEHICLE_NAME).click()
  await expect(page).toHaveURL(/\/fleet\/\d+/)

  await page.getByRole('link', { name: 'Book with Driver' }).click()
  await expect(page).toHaveURL(/\/book\?/)

  // Randomize the date window so repeated/parallel runs never collide with a leftover booking
  // still holding the same dates on this vehicle (the backend's double-booking guard blocks
  // overlapping PENDING/CONFIRMED bookings on the same vehicle).
  const offset = 20 + Math.floor(Math.random() * 300)
  const pickupLocation = `E2E Test Pickup ${Date.now()}`
  await page.locator('label:has-text("Start date") + input').fill(futureDateString(offset))
  await page.locator('label:has-text("End date") + input').fill(futureDateString(offset + 2))
  await page.locator('label:has-text("Pickup location") + input').fill(pickupLocation)

  // Name/phone/email are pre-filled from the logged-in account (see BookingView.vue's form
  // defaults) - nothing else to fill for a with-driver booking.
  await page.getByRole('button', { name: 'Confirm Booking' }).click()
  await expect(page.getByRole('heading', { name: 'Booking Received' })).toBeVisible()

  await page.goto('/account/bookings')
  const card = page.locator('div.rounded-xl', { hasText: pickupLocation }).first()
  await expect(card).toBeVisible()
  await expect(card.getByText('pending', { exact: true })).toBeVisible()

  // Cancelling here has no confirmation step (unlike logout's SweetAlert2 dialog) - it cancels
  // immediately on click, see MyBookingsView.vue's cancelBooking().
  await card.getByRole('button', { name: 'Cancel Booking' }).click()
  // A longer timeout here - the dev backend serves all parallel test workers at once, so this
  // request can queue up behind the other specs' API calls.
  await expect(card.getByText('cancelled', { exact: true })).toBeVisible({ timeout: 10000 })
})
