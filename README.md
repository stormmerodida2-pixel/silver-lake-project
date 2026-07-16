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

Copy `settings/.env.example` to `settings/.env` and fill in real values before going to production
(`SECRET_KEY`, `MPESA_*` credentials from Safaricom Daraja, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`).
`settings/base.py` reads it from that exact location - see the comment above `BASE_DIR` there.

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
Gmail address + [App Password](https://myaccount.google.com/apppasswords) to `settings/.env`
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

Runs at `http://localhost:5173`. Configure `VITE_API_BASE_URL` (the backend API root) and
`VITE_WHATSAPP_NUMBER` (the floating WhatsApp button's target number) in `frontend/.env`.

## Deployment

The app is deployment-ready apart from M-Pesa (which needs your own Safaricom production
registration - see below) once these env vars are set in `settings/.env`:

- `DATABASE_URL` — switches from local SQLite to MySQL (`mysql://USER:PASSWORD@HOST:PORT/NAME`).
- `AWS_STORAGE_BUCKET_NAME` + `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` — switches uploaded
  vehicle/driver photos and documents from local disk to S3-compatible object storage. Works with
  real AWS S3, Cloudflare R2, DigitalOcean Spaces, Backblaze B2, or anything else speaking the S3
  API (set `AWS_S3_ENDPOINT_URL` for anything that isn't real AWS S3). Local disk is fine for dev,
  but most hosts wipe it on every deploy - this must be set before going live.

Both are optional and independent - unset, the app behaves exactly as it does today. A `Procfile`
is included (`release: python manage.py migrate`, `web: gunicorn silverlake.wsgi`) for any
Heroku/Railway-style host that reads one.

### CI deploy (AWS EC2, free tier)

`.github/workflows/ci.yml`'s `deploy` job builds the root `Dockerfile` (backend API only - the
frontend is a separate static build, not part of this image), pushes it to ECR, then SSHes into
an EC2 instance to pull and restart it. EC2 (`t2.micro`/`t3.micro`, 750 hrs/month free for 12
months) was chosen over AWS App Runner specifically because App Runner has **no free-tier
allowance at all** - it bills per vCPU/memory-hour from the first second (roughly $5-15/month for
a small always-on service like this). The container runs `collectstatic` and `migrate` on every
start (see the Dockerfile's own comment for why - both need real `settings/.env` values that only
exist at container runtime, not at `docker build` time), then `gunicorn` on port 8000.

This needs a one-time AWS setup this repo can't do for you:
1. Create an ECR repository for the image.
2. Launch an EC2 instance (`t2.micro`/`t3.micro`, Ubuntu or Amazon Linux). Attach an **IAM
   instance role** with `AmazonEC2ContainerRegistryReadOnly` so the box can pull from ECR without
   any static AWS keys stored on it. Security group: allow 22 (SSH), 80/443 (public web traffic).
3. SSH in once and set the box up by hand: install Docker, install `nginx` and `certbot`
   (`sudo certbot --nginx` for a free auto-renewing Let's Encrypt certificate once a domain
   points at the instance), and configure nginx as a reverse proxy from 80/443 to
   `localhost:8000`. Also create `/home/<user>/silverlake.env` on the box containing the real
   production env vars (`SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` pointing at an RDS MySQL
   instance, `AWS_STORAGE_BUCKET_NAME` etc. pointing at a real S3 bucket, `MPESA_*`,
   `BEHIND_HTTPS_PROXY=true` since nginx terminates TLS, ...) - CI only ships and restarts the
   container, it never touches this file or the box's nginx/TLS config.
4. Create an IAM user (separate from the instance role, scoped to ECR push only) for GitHub
   Actions, and add these as GitHub repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `AWS_REGION`, `ECR_REPOSITORY`, plus `EC2_HOST` (the instance's public IP or Elastic IP),
   `EC2_USER` (e.g. `ubuntu`), `EC2_SSH_PRIVATE_KEY` (the instance's key pair, private half).
5. Set two GitHub repo **variables** (Settings → Secrets and variables → Actions → Variables):
   `AWS_DEPLOY_READY=true` (the whole `deploy` job is skipped, not failed red, until this is set),
   and `PRODUCTION_URL` (e.g. `https://your-domain.com`, no trailing slash - used to build the
   frontend with the right API base URL). Also add `WHATSAPP_NUMBER` as a variable (international
   format, no `+`, e.g. `254700000000`) for the floating WhatsApp button.

The frontend is built fresh on every deploy (with the real `PRODUCTION_URL` baked in via Vite env
vars, unlike the `frontend` job above which only compile-checks it) and copied into nginx's
serving root over SSH. The one-time nginx + certbot reverse-proxy setup (serving the frontend at
`/` and proxying `/api/`, `/sitemap.xml`, `/static/` to the container, plus `/media/` served
directly from a host-mounted volume since Django doesn't serve `MEDIA_URL` itself when
`DEBUG=False`) is done by hand on the box, not by CI - see the Dockerfile and `deploy` job's own
comments for the exact shape.

What's still genuinely external, not something more code can fix:

- **M-Pesa production credentials** — `MPESA_*` in `.env` are currently Safaricom's shared public
  *sandbox* values. Going live needs your own Paybill (via a bank or Safaricom Business) and a
  Daraja "Go Live" request for the Lipa Na M-Pesa Online product, which itself requires a real
  domain to already be live (for `MPESA_CALLBACK_URL`).
- **A real domain** and the AWS account/setup above.
- **A production email sender** — `EMAIL_HOST_USER` is currently a personal Gmail address; works,
  but a branded address is worth it before launch.
- Rotate any dev/test account passwords before going live.

## Testing & CI

```bash
python manage.py test accounts.tests fleet.tests drivers.tests bookings.tests payments.tests reviews.tests announcements.tests blog.tests notifications.tests core.tests --settings=settings.local
cd frontend && npm run build
```

Both run automatically on every push/PR via `.github/workflows/ci.yml`. Passing `test` as a bare
app label (e.g. `manage.py test blog`) doesn't reliably discover tests in this layout — always use
the dotted `app.tests` form shown above.


