import { expect, test } from '@playwright/test'

import { E2E_CUSTOMER_EMAIL, E2E_PASSWORD, E2E_VEHICLE_NAME, login } from './helpers'

test('a logged-in customer can favorite a vehicle and see it on My Favorites', async ({ page }) => {
  await login(page, E2E_CUSTOMER_EMAIL, E2E_PASSWORD)

  await page.goto('/fleet')
  // Each VehicleCard renders as a single <a class="group ..."> wrapping the whole card.
  const card = page.locator('a.group').filter({ hasText: E2E_VEHICLE_NAME })
  await card.getByRole('button', { name: 'Add to favorites' }).click()
  await expect(card.getByRole('button', { name: 'Remove from favorites' })).toBeVisible()

  await page.goto('/account/favorites')
  await expect(page.getByText(E2E_VEHICLE_NAME)).toBeVisible()

  // Unfavoriting from the favorites page removes the card immediately.
  await page.getByRole('button', { name: 'Remove from favorites' }).click()
  await expect(page.getByText(E2E_VEHICLE_NAME)).not.toBeVisible()
  await expect(page.getByText('No favorites yet')).toBeVisible()
})
