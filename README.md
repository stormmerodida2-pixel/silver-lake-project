# SilverLake Car Rentals

Car hire platform for SilverLake Car Rentals (Kisumu, Kenya) — book with a driver or self-drive,
pay via M-Pesa or card, browse the fleet and driver profiles.

## Structure

- Django + Django REST Framework API at the repo root (`accounts`, `fleet`, `drivers`, `bookings`, `payments`, `reviews`, ...)
- `frontend/` — Vue 3 + Vite + Tailwind CSS + Pinia SPA
- `venv/` — Python virtual environment for the backend

## Backend

```bash
venv\Scripts\activate
python manage.py migrate
python manage.py createsuperuser   # first time, for /admin/
python manage.py runserver
```

API runs at `http://localhost:8000/api/`, admin at `http://localhost:8000/admin/`.

Copy `.env.example` to `.env` and fill in real values before going to production
(`SECRET_KEY`, `MPESA_*` credentials from Safaricom Daraja).

### Auth

Customers must register/log in (JWT, via `djangorestframework-simplejwt`) before creating a booking.
Fleet, driver profiles, and reviews stay public/read-only for anonymous visitors and are not gated.
`/admin/` staff login is separate (Django's own session auth) and lets you add vehicles, upload multiple
gallery photos per vehicle, manage drivers, and approve reviews.

- `POST /api/auth/register/` — `{full_name, email, phone_number, password}` → creates an **inactive** account and emails an activation link
- `POST /api/auth/activate/<uid>/<token>/` — activates the account from the emailed link
- `POST /api/auth/login/` — `{username: email, password}` → returns `{user, access, refresh}` (fails until activated)
- `GET /api/auth/me/` — current user (requires `Authorization: Bearer <access>`)
- `POST /api/auth/password-reset/` — `{email}` → always returns a generic success message, emails a reset link if the address is registered
- `POST /api/auth/password-reset/confirm/` — `{uid, token, new_password}`
- `POST /api/auth/change-password/` — `{old_password, new_password}` (requires auth)

Activation/reset emails go out via Gmail SMTP. Until you add a real Gmail address + [App Password](https://myaccount.google.com/apppasswords)
to `.env` (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`), emails are printed to the `runserver` console instead
of actually sending (see `EMAIL_BACKEND` fallback in `settings.py`) — grab the activation/reset link from there while testing.

In `DEBUG` mode, CORS allows any localhost origin (Vite's port shifts to 5174+ if 5173 is busy); production
locks back down to the `CORS_ALLOWED_ORIGINS` env var.

### Deposits

Each booking has a `total_amount` computed from the vehicle's daily rate × nights. Customers can pay a
30% deposit or the full balance via M-Pesa STK Push (`Booking.DEPOSIT_PERCENT` in `bookings/models.py`).
The first payment on a booking must cover at least the deposit; once paid, the booking auto-confirms.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`. Configure `VITE_API_BASE_URL` and `VITE_WHATSAPP_NUMBER` in `frontend/.env`.

## Known gaps (next steps)

- Booking dates aren't checked against existing bookings yet — no double-booking prevention.
- Card payments are stubbed in the UI pending a gateway choice (e.g. Flutterwave, Pesapal).
- M-Pesa STK Push needs real Daraja credentials (`MPESA_CONSUMER_KEY`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`) — currently points at the sandbox.
- No image uploads seeded yet for vehicles/drivers (admin panel supports it, including multiple gallery photos per vehicle).
- JWT access tokens last 1 day (extended from SimpleJWT's 5 min default) but aren't auto-refreshed — the stored refresh token isn't used yet, so users must log in again after a day.
- Real Gmail SMTP credentials aren't set yet — activation/reset emails currently just print to the console (see Auth section above).
