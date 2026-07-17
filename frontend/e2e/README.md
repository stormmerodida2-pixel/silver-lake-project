# End-to-end tests (Playwright)

These drive a real browser against the real app - the actual golden paths a customer or
admin would take, not mocked API calls. Playwright only starts the **frontend** dev server
for you; the Django **backend** must already be running separately, with `seed_e2e_data`
applied.

## Running locally

1. Start the backend (from the repo root, with your venv active):
   ```
   python manage.py migrate
   python manage.py seed_e2e_data
   python manage.py runserver
   ```
   `seed_e2e_data` creates a fixed, already-active customer account, a fixed superadmin
   account, and one dedicated bookable vehicle ("E2E Test Vehicle") - see
   `core/management/commands/seed_e2e_data.py` for the exact credentials. It refuses to run
   unless `DEBUG=True`, so it can never be run against a real/production database.

2. In `frontend/`, run the suite:
   ```
   npm run test:e2e
   ```
   This starts `npm run dev` automatically (reusing an already-running one if you have it
   open) and points Playwright at `http://localhost:5173`.

## What's covered

- **smoke.spec.js** - home page loads, nav → Fleet works, the seeded vehicle appears on the
  fleet listing, and the mobile hamburger menu opens/closes correctly (regression coverage
  for the NavBar mobile header fix).
- **auth.spec.js** - customer login/logout, and an invalid-password error message.
- **booking.spec.js** - the full customer booking flow: browse → vehicle detail → book with
  driver → confirmation → appears in My Bookings → cancel. Randomizes its date window each
  run so repeated/parallel runs never collide with a leftover booking on the same vehicle.
- **admin.spec.js** - superadmin login, the Dashboard loads, the Fleet Map's searchable
  vehicle list loads, and System Health loads.

## What's deliberately not covered

- **Registration and email activation** - the real flow requires clicking a link in a real
  email, which isn't something to depend on in an automated suite. `seed_e2e_data` creates
  already-active accounts specifically to skip this and still exercise everything
  downstream of login.
- **Real M-Pesa payment completion** - the sandbox STK Push flow requires entering a PIN on
  a phone; the booking flow test stops at booking creation, which is the part that's ours to
  regress.
