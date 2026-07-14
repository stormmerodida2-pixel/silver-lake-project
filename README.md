# SilverLake Car Rentals

Car hire platform for SilverLake Car Rentals (Kisumu, Kenya) — book with a driver or self-drive,
pay via M-Pesa or card, browse the fleet and driver profiles. Built as a Django REST Framework
API with a Vue 3 single-page frontend, covering the whole loop from a customer's first booking
through payment, driver payout, and refund.

## What's here

- **Public site** — fleet browsing (filterable by category), driver profiles, customer reviews,
  a marketing blog, and the booking/payment flow itself.
- **Customer accounts** — JWT auth with email activation, password reset, and a self-service
  bookings/profile area. A customer with no account can still pay for a booking a driver set up
  for them via a no-login link.
- **Driver portal** — a driver's own dashboard: their vehicles, live bookings, trip lifecycle
  (acknowledge → start → end → complete), collecting payment on the spot, and applying to join as
  a driver-partner with their own vehicle.
- **Staff admin dashboard** — a custom Vue app at `/admin` (not Django's built-in admin) covering
  fleet, bookings, drivers, payments, payouts, refunds, reviews, blog, announcements, an
  in-app notification system, and a full activity log. Two permission tiers (support staff vs.
  superadmin) gate anything destructive or financial.
- **Multi-tenant fleet partners** — a `FleetPartner` organization can register its own fleet and
  staff, scoped to see only their own data, while every client payment still routes through
  SilverLake's own Paybill so the platform fee is never at risk.
- **Payment trust & safety** — cash and card payments are self-reported and require independent
  confirmation before a payout is created; a driver's cash-acceptance can be disabled per-driver by
  a superadmin; the no-login payment link expires after a grace period past the trip's end date.
  See `PAYMENT_SECURITY.md` for the full rationale.

For the deep-dive on how any of this actually works end to end, see `PLATFORM_OVERVIEW.md`.

## Structure

- Django + Django REST Framework API at the repo root (`accounts`, `fleet`, `drivers`,
  `bookings`, `payments`, `reviews`, `blog`, `announcements`, `notifications`, `core`)
- `frontend/` — Vue 3 + Vite + Tailwind CSS + Pinia SPA
- `venv/` — Python virtual environment for the backend
- `settings/` — split by environment (`local`, `development`, `production`) rather than a single
  settings module; see the docstring at the top of each file

## Backend

```bash
venv\Scripts\activate
python manage.py migrate
python manage.py createsuperuser   # first time, for the custom admin at /admin (frontend route)
python manage.py runserver --settings=settings.local
```

API runs at `http://localhost:8000/api/`. Django's own built-in admin is also reachable at
`http://localhost:8000/admin/` in local/dev settings (`DEBUG=True`) as a low-level data-inspection
convenience only — it's never registered at all once `DEBUG=False` (see `settings/production.py`),
and isn't where staff actually manage the platform day to day; that's the Vue app at `/admin`.

Copy `.env.example` to `.env` and fill in real values before going to production (`SECRET_KEY`,
`MPESA_*` credentials from Safaricom Daraja, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`).

Want the fleet/reviews/driver pages to look populated for a demo instead of empty? Run:

```bash
python manage.py seed_demo_data --settings=settings.local
```

Safe to re-run - it only adds data, keyed so it never duplicates itself or touches anything real
already in the database.

### Auth

Customers must register/log in (JWT, via `djangorestframework-simplejwt`) before creating a
booking. Fleet, driver profiles, reviews, and the blog stay public/read-only for anonymous
visitors and are not gated.

- `POST /api/auth/register/` — `{full_name, email, phone_number, password}` → creates an **inactive** account and emails an activation link
- `POST /api/auth/activate/<uid>/<token>/` — activates the account from the emailed link
- `POST /api/auth/login/` — `{username: email, password}` → returns `{user, access, refresh}` (fails until activated)
- `GET /api/auth/me/` — current user (requires `Authorization: Bearer <access>`)
- `POST /api/auth/password-reset/` — `{email}` → always returns a generic success message, emails a reset link if the address is registered
- `POST /api/auth/password-reset/confirm/` — `{uid, token, new_password}`
- `POST /api/auth/change-password/` — `{old_password, new_password}` (requires auth)

Access tokens are short-lived; the frontend's axios interceptor silently refreshes on a 401, so
this doesn't require the user to log in again mid-session.

Activation/reset/every other transactional email goes out via Gmail SMTP. Until you add a real
Gmail address + [App Password](https://myaccount.google.com/apppasswords) to `.env`
(`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`), emails are written to `sent_emails/` instead of
actually sending — open the `.html` file there to grab an activation/reset link while testing.

In `DEBUG` mode, CORS allows any localhost origin (Vite's port shifts to 5174+ if 5173 is busy);
production locks back down to the `CORS_ALLOWED_ORIGINS` env var.

### Deposits & payouts

Each booking has a `total_amount` computed from the vehicle's daily rate × nights (self-drive
carries a 3% surcharge). Customers pay a 30% deposit or the full balance via M-Pesa STK Push,
cash, or (once a payment gateway is chosen) card. Once a with-driver booking is paid in full, a
`DriverPayout` is queued automatically for the driver or fleet partner who owns the vehicle,
minus SilverLake's platform fee — a superadmin marks it disbursed once the money's actually been
sent. See `PLATFORM_OVERVIEW.md` §6-7 for the full flow, including how cash payments are
independently verified before a payout can go out.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`. Configure `VITE_API_BASE_URL` in `frontend/.env`.

## Testing & CI

```bash
python manage.py test accounts.tests fleet.tests drivers.tests bookings.tests payments.tests reviews.tests announcements.tests blog.tests notifications.tests core.tests --settings=settings.local
cd frontend && npm run build
```

Both run automatically on every push/PR via `.github/workflows/ci.yml`. Passing `test` as a bare
app label (e.g. `manage.py test blog`) doesn't reliably discover tests in this layout — always use
the dotted `app.tests` form shown above.

## Before going live

Not broken, but a conscious decision needed before real customers/real money:

- **M-Pesa is still pointed at Safaricom's sandbox** — no real payment can confirm until you have
  production Daraja credentials.
- **No real domain/HTTPS yet** — `MPESA_CALLBACK_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  and `FRONTEND_URL` are all still `localhost`; Safaricom's servers can't reach a callback URL
  that isn't publicly reachable over HTTPS.
- **File storage is local disk** — every uploaded photo/document won't survive a redeploy until
  this moves to an object storage backend (S3-compatible - AWS S3, Cloudflare R2, DigitalOcean
  Spaces all work the same way here).
- **Nothing is deployed anywhere yet** — a hosting decision hasn't been made.

The full, continuously-updated list lives in `PLATFORM_OVERVIEW.md` §13.
