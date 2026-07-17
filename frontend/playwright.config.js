import { defineConfig, devices } from '@playwright/test'

// Assumes the Django backend (manage.py runserver, default :8000) is already running with
// `seed_e2e_data` applied - Playwright only starts the frontend dev server itself. See
// frontend/e2e/README.md for the full local setup.
export default defineConfig({
  testDir: './e2e',
  // manage.py runserver is a single process - PBKDF2 password hashing on /login is CPU-bound
  // enough that several tests logging in at once queue up behind each other and blow past
  // Playwright's default timeouts. One worker keeps this suite reliable against a dev server.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
})
