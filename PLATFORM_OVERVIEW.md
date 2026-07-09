# SilverLake Car Rentals — Platform Overview

*As of 2026-07-05.* This document is a complete walkthrough of what's actually built, end to end —
from a customer creating an account through to a driver getting paid. It's written for anyone
running the business, not just developers. Where something is still incomplete or needs a
decision before launch, it's called out explicitly rather than glossed over.

---

## 1. Accounts & Authentication

- **One login system for everyone.** Customers, driver-partners, and staff all log into the same
  account system — what they can see and do afterward depends on their role (below), not a
  separate login page.
- **Sign-up requires email activation.** A new customer registers with name, email, phone, and
  password; the account starts inactive and an activation email (via Gmail SMTP) has to be
  clicked before they can log in. This keeps out throwaway/fake emails.
- **Password reset** is self-service (forgot password → email link → set new password), and a
  logged-in user can change their password directly from their account.
- **A "My Profile" page** lets a customer update their own name and phone number. Email is
  deliberately not editable there — it doubles as the login username, and changing it has no
  re-verification flow yet, so that stays a "contact us" request for now.
- **JWT-based sessions.** Logging in issues a short-lived access token (15 min) plus a
  longer-lived refresh token (14 days); the frontend silently refreshes in the background, so
  the short lifetime costs nothing in usability.
- **Logging out, changing your password, or resetting a forgotten one actually revokes the
  session server-side** — not just clearing the browser's local storage. A token that's been
  copied or stolen stops working the moment any of those three things happen, instead of quietly
  continuing to work for up to 14 days regardless.
- **Driver-partner accounts are created for you.** A driver never signs up directly — once their
  application is approved, the system creates their login automatically and emails them an
  invite (see §4).
- **Your role stays in sync.** The browser refreshes your profile (name, staff/driver status)
  the moment you navigate back to the main site from the driver portal — so if your driver
  application gets approved while you're still logged in, you don't need to log out and back in
  to see the change take effect.

## 2. Roles

| Role | Who | What they can do |
|---|---|---|
| **Customer** | Anyone who registers | Browse the fleet, book a trip, pay, view their own bookings, leave a review after a completed trip |
| **Driver-partner** | Approved via the "Become a Driver" flow | Everything a customer can do, plus: submit their own vehicle(s) for approval, mark themselves away/available, log walk-up bookings and cash payments for their own vehicle, see their own payout history |
| **Support Staff** (`is_staff`) | Internal team | Day-to-day admin: view users/bookings/payments, moderate reviews, approve driver applications & vehicle submissions, suspend/activate accounts |
| **Super Admin** (`is_superuser`) | Owner/seniogr staff | Everything Support Staff can do, **plus** anything that moves money or changes fleet composition: create/edit/delete users, create/edit/delete vehicles, verify & pay out driver payouts, issue refunds, permanently delete reviews |

The split exists so day-to-day operations don't require the same access as financial actions.
Every action in the second column that touches money or someone's access level is now recorded
in an **Activity Log** admin staff can review (who did what, and when — see §10).

## 3. The Fleet

- Vehicles are either **self-drive**, **with-driver**, or both, set per vehicle.
- **Fleet types** (e.g. "Executive SUV") are admin-managed records, not a fixed list in code —
  superadmins add/edit/remove them from **Admin → Fleet Types**. Every vehicle, driver-submitted
  car, and "Become a Driver" application picks its category from this same list. A fleet type
  still assigned to any vehicle, submission, or application can't be deleted (blocked, not
  silently orphaned) — rename or leave it in place instead.
- Each vehicle tracks **insurance and inspection expiry dates**. If either lapses, the vehicle
  automatically disappears from what customers see — no manual step required, so an expired
  vehicle can't accidentally keep taking bookings.
- A vehicle also disappears from public listings while its assigned driver has marked themselves
  **away**, or if that driver has been suspended (see §4) — the fleet listing always reflects who's
  actually available right now.
- Availability for a given date range is computed live from existing bookings — a vehicle already
  booked for part of a date range simply won't show as available for it.

## 4. Becoming a Driver-Partner

This is the platform's main growth lever beyond buying more vehicles directly (see the separate
business-model pitch for the economics).

1. Anyone can apply publicly via "Become a Driver," describing their vehicle and experience.
2. Staff review the application (approve/reject, with notes) from the admin Drivers page.
3. **Approving an application creates a live `Driver` record and a login account for them in one
   step**, and emails them a portal invite.
4. From their own **Driver Dashboard**, a driver can:
   - Submit vehicle(s) of their own for approval (minimum 2 photos + logbook document required;
     staff approve/reject before it goes live)
   - Mark themselves **away** with a reason (visible only to admin — customers just see the
     vehicle disappear) and mark themselves available again
   - Create a booking directly for a walk-up client who booked in person, with no login required
     from the customer
   - Record a **cash payment** for one of their own bookings
   - View their own payout history
   - See every booking an online customer has placed against them, and **approve** a new one to
     acknowledge they've seen it — this is informational only, it doesn't block or delay the
     booking itself, which still confirms on the customer's deposit either way
   - Mark a fully-paid trip **complete** once it's done, which sends the customer their
     review-invite email — previously the only way to do this was an admin manually changing
     the booking's status
5. The driver is **emailed the moment an online customer books them** — not only once the
   deposit is paid — so they find out as early as possible and can plan around it. A driver's
   own walk-up bookings skip this (they already know, having just created it themselves).
6. Staff can **suspend** a driver (with a reason, which emails the driver) — this hides all of
   their vehicles immediately, same as marking away. A suspended driver sees "Currently
   Suspended" on the site instead of the normal driver CTA; an active driver sees a link to their
   dashboard in the main nav instead.

## 5. Booking a Trip

- A customer picks a vehicle, dates, and (if the vehicle allows it) whether they're driving
  themselves or want a driver. Self-drive requires uploading a driving license and ID/passport
  document at booking time. There's no separate "pick a driver" step — booking "with driver" on
  a vehicle that has one automatically assigns that vehicle's own driver.
- **New bookings can't start in the past** — this is checked at creation only, so an existing
  booking that's simply sat pending for a while is never retroactively invalidated by an
  unrelated edit.
- Overlapping bookings for the same vehicle (or the same driver) are rejected outright.
- A booking starts **Pending**, and moves to **Confirmed** automatically once a **30% deposit**
  is paid. It later becomes **Ongoing**/**Completed** via staff updating status, or the driver
  marking their own trip complete once it's fully paid (completing a trip is blocked if there's
  still a balance outstanding).
- Once completed, the customer can leave a **review** of the driver/trip (one per booking).
- A customer (or staff) can **cancel** a booking any time before it's completed. As of today,
  cancelling a booking that already had money paid against it automatically creates a **Refund**
  record for admin to action (see §7) — it no longer just disappears with no record of money
  owed back.

## 6. Payments

- **M-Pesa STK Push** (Paybill **400400**) is the primary payment rail — a customer gets a prompt
  on their phone and pays directly into the till.
- **Cash payments**: a driver can record a cash payment they collected on the spot (e.g. a
  walk-up client). This is flagged for admin review before it can trigger a real payout — see §7.
- Every payment path rejects a **zero or negative amount**, and refuses to accept a payment
  against a booking that's already cancelled or completed.
- The M-Pesa callback (Safaricom telling us a payment succeeded) is protected by a private secret
  baked into the callback URL — without it, the request is rejected outright. This closes off a
  theoretical way someone could have faked a "payment successful" notification.
mnm 
- **Rate limiting** caps how many times the sensitive public endpoints can be hit in a given
  window: login (10/min), registration (5/hour), password reset requests (5/hour), and both
  M-Pesa STK push triggers (5/min) — the last one specifically because each request can fire a
  real prompt on a customer's phone, so it's the one most worth capping if a link ever leaked.

## 7. Payouts, Refunds & Trust

This is the part of the system most exposed to someone's word being wrong, since a driver
self-reporting a cash payment isn't independently verified the way M-Pesa is.

- **Driver payout math:** for a with-driver booking, SilverLake keeps a **15% platform fee**;
  the driver is owed the remaining **85%**. Self-drive bookings have no driver payout — SilverLake
  keeps the full amount.
- **A payout is only created once the booking is fully paid** — not merely deposited — so the
  business never queues a payout for money it hasn't actually collected yet.
- **Cash-sourced payouts need explicit sign-off.** If any payment behind a payout was cash
  (self-reported, no bank confirming it), that payout is flagged "Needs Verification" and can't
  be marked paid until a superadmin explicitly verifies it. M-Pesa-confirmed payouts skip this,
  since Safaricom's own confirmation already is the verification.
- **Refunds are tracked, not automated.** There's no live M-Pesa refund API wired up — instead,
  cancelling a paid booking creates a `Refund` record automatically, which shows up on the admin
  Refunds page as "Pending" until a superadmin sends the money back by hand and marks it
  "Issued" (with a reference number).
- **Cancelling voids any unpaid payout.** If a booking's driver payout hadn't been disbursed yet
  when the booking got cancelled, that payout is automatically voided — a cancelled trip can't
  still owe a driver their cut. This also covers a payment that was already in flight before the
  cancellation and only confirms afterward (e.g. an M-Pesa prompt sent moments before the
  customer cancelled) — it can never queue a new payout, and instead tops up the refund to match
  what's actually been paid.
- **A payment retry can't quietly become a double payment.** If an M-Pesa prompt is still
  possibly active (sent in the last minute), trying again on the same booking is blocked with a
  clear message instead of firing a second concurrent prompt.
- **Every sensitive admin action is recorded in the Activity Log** — who did it and when. This
  covers payout verify/mark-paid, refund mark-issued, suspend/activate, role changes, editing or
  deleting a booking/vehicle/review, managing a vehicle's gallery, and approving/rejecting a
  driver application or vehicle submission.
- **Deleting a user, driver, or vehicle can't take their financial history with them.** A
  customer's bookings, a driver's payouts, and a vehicle's booking record are all protected —
  trying to delete an account or vehicle that still has any of these on file is blocked with a
  clear message ("suspend the account instead") rather than silently cascading the deletion
  through every payment, payout, and refund tied to it.
- **Django's own built-in admin site is a local-development tool only, not a second production
  admin surface.** It's only reachable when `DEBUG` is on. It used to be reachable in production
  too, and its own bulk actions bypassed two of the safeguards above (cash-payout verification
  and driver-rating recalculation on review approval) — those are fixed regardless, but the real
  admin surface for day-to-day use is always the Vue dashboard described in §10.

## 8. Reviews

Customers can review a completed trip once; staff moderate (approve/reject) before a review is
public. Reviews are tied to both the booking and the driver, and a driver's displayed rating is
recalculated automatically (the average of their approved reviews) every time one is approved,
rejected, or deleted — it doesn't just sit at the default forever.

- **The public reviews page and home page are view-only.** There's no way to submit a review
  from either — the only legitimate way to leave one is reviewing your own completed booking
  (from My Bookings, while logged in). The public API is read-only too, not just the UI.
- **Driver identity is never shown publicly on a review.** The public listing shows the rating,
  comment, and customer name only — not which driver or booking it's about. Staff still see that
  detail on the admin Reviews page, since they need it to moderate accurately.

## 9. Email Notifications

Sent automatically, using branded HTML templates, via Gmail SMTP:

- Account activation (customer)
- Booking confirmed (customer)
- New booking, please review (driver) — sent the moment an online customer books them
- Trip completed / review invite (customer)
- Cash payment recorded (customer) — an independent check, since they didn't initiate it
- Cash payment recorded (driver) — confirms the amount and that it's queued for admin verification
- Driver portal invite (driver)
- Driver suspended, with reason (driver)
- Driver marked themselves away (admin, BCC to staff)
- New driver application submitted (admin)
- New vehicle submitted by a driver (admin)

Every email send is wrapped so a failure (bad SMTP config, etc.) never blocks the underlying
action — a booking still confirms even if the confirmation email fails to send.

## 10. The Admin Dashboard

A custom Vue dashboard at `/admin` (not Django's built-in admin) — everything staff need lives
in one consistent UI:

- **Dashboard** — revenue collected, platform fees earned, payouts owed/paid, bookings by status,
  user/driver counts (including pending applications and drivers currently away), fleet counts,
  pending reviews, and **pending refunds**.
- **Users** — list, edit details, grant/revoke staff & superadmin roles, suspend/activate,
  create accounts directly.
- **Drivers** — manage live drivers plus the driver-application and vehicle-submission review
  queues, all in one page.
- **Bookings** — full oversight, manual status changes, and (superadmin only) editing the
  booking itself — e.g. fixing a booking assigned to the wrong driver.
- **Fleet** — full vehicle CRUD, toggle availability, assign which driver drives a company-owned
  vehicle (a driver-partner's own submitted car is assigned automatically), and manage a
  vehicle's photo gallery beyond its single cover image.
- **Fleet Types** — add/edit/remove the vehicle categories offered across the site (used to be a
  fixed enum in code); a type still in use by a vehicle, submission, or application can't be
  deleted.
- **Reviews** — approve/reject, delete.
- **Payouts** — the driver payout ledger; verify and mark paid.
- **Refunds** — the refund ledger; mark issued.
- **Payments** — the raw payment log.
- **Activity Log** — who performed which sensitive action, and when.

Every page is mobile-responsive: the sidebar collapses to a horizontal scrolling nav, stat grids
drop to a single column, and every table scrolls horizontally instead of breaking the layout.

## 11. Legal & Compliance

- Public **Terms**, **Privacy**, and **Refund Policy** pages.
- Self-drive bookings require a license and ID/passport on file before the booking is valid.
- Vehicles with lapsed insurance or inspection are hidden automatically (§3).

## 12. What's Tested

173 automated backend tests currently cover booking validation, payment guards, payout timing and
verification, refund creation/voiding (including late payments arriving after cancellation), the
audit log (now covering every sensitive admin action, not just the earliest ones), the
delete-protection rules (including fleet-type deletion blocked while still in use), rate limiting,
the STK-push retry cooldown, session/token revocation on logout and password change, driver
booking notifications/acknowledgment, driver-defaulting, driver-side trip completion, admin driver
assignment, driver rating recalculation, admin booking edits, vehicle gallery management, payment
status polling, self-service profile updates, the public reviews API's read-only/no-driver-details
restrictions, fleet-type CRUD and permission tiers, and the Django admin's own bulk-action
fixes — run with:
```
cd silverlake
python manage.py test
```

## 13. What's Still Open Before Launch

Not broken, but worth a conscious decision before going fully live:

- **Real M-Pesa production credentials** — still pointed at Safaricom's sandbox.
- **`MPESA_CALLBACK_URL` is still a placeholder domain** — Safaricom's servers need to reach this
  over the public internet with a valid HTTPS cert before any STK push (sandbox or production)
  can ever confirm. Same goes for `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS`/`FRONTEND_URL`, still
  all `localhost`.
- **File storage is local disk** — uploaded documents/photos won't survive a server redeploy as
  currently configured.
- **Payment/booking links don't expire** — the no-login payment link and driver trip-completion
  link are permanent once issued.
- **Refund disbursement is manual** — there's no automated M-Pesa refund API integration, only a
  tracked record of what's owed.
- Whether **company-employed drivers** should be paid the same 85% commission as driver-partners
  who own their own vehicle is a business decision the system doesn't currently distinguish
  between (both are just "the assigned driver" today).

See `PAYMENT_SECURITY.md` for a deeper dive specifically on the payment-trust fixes, and the
separate business-model document for the revenue/growth reasoning behind the driver-partner
marketplace.
