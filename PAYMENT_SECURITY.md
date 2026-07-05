# Payment Trust & Security Notes

This document explains a set of gaps found in how money moves through the app, and what was
fixed. It's written for anyone running the business, not just developers — if you're deciding
whether it's safe to go live, or reviewing what changed, start here.

## Why this matters

Two features let money-related state change *without* a real payment gateway confirming
anything happened: a driver recording a cash payment on the spot, and (before this fix) the
M-Pesa "payment succeeded" callback. Both are places where the system has to **trust** a claim
instead of verifying it — which is exactly where fraud gets in.

## What was found, and what was fixed

### 1. A driver could fabricate a cash payment to trigger their own payout

**The gap:** Recording a cash payment immediately marked it "successful" (there's no bank to
confirm cash against) and immediately queued the driver's *full trip payout* — before any admin
looked at it. A driver could claim a cash payment that never happened and get themselves queued
for a real payout with zero money actually collected.

**The fix:**
- Any payout that came from a cash payment is now flagged **"Needs Verification."** An admin
  must explicitly click **Verify** (Manage → Payouts) before **Mark Paid** becomes available.
  M-Pesa-confirmed payouts are unaffected — they can still be marked paid directly, since
  Safaricom's own confirmation is the verification.
- The customer is emailed the moment a cash payment is recorded on their booking — an
  independent check, since they didn't initiate it themselves. If they never actually paid,
  this is what tips them off to dispute it.

*Code:* `silverlake/payments/services.py` (`record_cash_payment`), `DriverPayout.needs_verification`
/ `is_verified` in `silverlake/payments/models.py`, verify action in `silverlake/core/views.py`.

### 2. The M-Pesa callback could be forged

**The gap:** Safaricom's payment-confirmation callback isn't signed or authenticated in any way —
it's just a POST to a URL we control. The `CheckoutRequestID` it's keyed on is also visible to
the customer's own browser when a payment starts. In theory, anyone with browser dev tools could
have replayed that ID to their own copy of the callback and marked their own booking "paid"
without ever sending real money.

**The fix:** The callback URL now requires a random secret path segment
(`MPESA_CALLBACK_SECRET` in `.env`) that's never sent to the client. Without the correct secret,
the callback is rejected outright (404) — no payment gets touched.

*Code:* `silverlake/payments/views.py` (`mpesa_callback`), `silverlake/payments/mpesa.py`
(appends the secret automatically when starting a payment).

### 3. Payment amounts had no floor, and closed bookings could still receive payments

**The gap:** Both the M-Pesa and cash payment paths only checked that an amount wasn't *too
high* — nothing stopped a **zero or negative** amount from being recorded as a "successful"
payment once a booking's deposit was already paid, which would have quietly corrupted the
running total of what a customer had paid. Separately, neither path checked whether a booking
was already **cancelled or completed** — a driver could still record a cash payment (or a
customer could still trigger an M-Pesa prompt) against a booking that was already closed out.

**The fix:** Both payment paths now reject any amount that isn't strictly greater than zero, and
refuse to accept a payment against a booking that's already cancelled or completed.

*Code:* `silverlake/payments/services.py` (`initiate_stk_push_payment`, `record_cash_payment`),
`silverlake/payments/serializers.py` (`min_value` on the amount fields).

## What's still open (not fixed, flagging for a decision)

- **Payment/booking links never expire.** `customer_token` and `driver_token` (used for the
  no-login payment page and the driver trip-completion link) are permanent. If one leaks, whoever
  has it can view that booking's details indefinitely. Low practical harm, but worth an expiry
  or rotation mechanism eventually.
- **No rate limiting** on public endpoints — registration, login, password reset, and now the
  no-login payment page. The payment page specifically could be hit repeatedly to spam a real
  client's phone with M-Pesa prompts if a link leaked.
- Broader pre-launch items (real M-Pesa production credentials, `DEBUG=True`, local-disk file
  storage, no CI running the test suite automatically) are tracked separately and unaffected by
  this work.

## How this is tested

66 automated backend tests cover the booking/payment/payout logic (`silverlake/bookings/tests.py`,
`silverlake/payments/tests.py`, `silverlake/core/tests.py`), including every scenario described
above — wrong/missing callback secret, zero/negative amounts, and payments against closed
bookings are all explicitly tested to fail the way this document says they should.

Run them with:
```
cd silverlake
python manage.py test
```
