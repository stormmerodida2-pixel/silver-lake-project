import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from drivers.models import Driver
from fleet.models import Vehicle

from .validators import validate_file_size

DOCUMENT_EXTENSIONS = FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])


class ServiceType(models.TextChoices):
    WITH_DRIVER = 'with_driver', 'Book with Driver'
    SELF_DRIVE = 'self_drive', 'Self Drive'


class BookingStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    ONGOING = 'ongoing', 'Ongoing'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class BookingSource(models.TextChoices):
    ONLINE = 'online', 'Online'
    DRIVER_ONSITE = 'driver_onsite', 'Driver (on-site)'


# Bookings in these statuses hold the vehicle; cancelled/completed ones don't block dates.
BLOCKING_BOOKING_STATUSES = [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ONGOING]

# How long an assigned driver has to acknowledge an online booking before it's considered
# overdue (see Booking.acknowledgment_deadline / payments.scheduler's automated escalation
# sweep) - a same-day pickup gets a tighter window than one booked further in advance, since a
# customer who needs a car today can't wait as long to find out the driver has actually seen it.
ACKNOWLEDGMENT_DEADLINE_SAME_DAY = timedelta(hours=1)
ACKNOWLEDGMENT_DEADLINE_FUTURE = timedelta(hours=2)

# Self-drive costs more than the vehicle's own with-driver rate - the customer is driving
# SilverLake's own vehicle themselves, which carries more risk/liability than a booking with a
# driver at the wheel. Applied to the whole booked total (see Booking.save()), not per day.
SELF_DRIVE_SURCHARGE_PERCENT = Decimal('3')


class Booking(models.Model):
    DEPOSIT_PERCENT = Decimal('30')
    # SilverLake's cut of a with-driver booking; the rest is paid out to the assigned driver.
    # Self-drive bookings have no driver payout, so the platform keeps the full amount either way.
    PLATFORM_FEE_PERCENT = Decimal('15')

    # PROTECT, not CASCADE - deleting a user shouldn't silently take their payment/payout/
    # refund history with them. An account with bookings on file has to be suspended, not deleted.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bookings')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='bookings')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)

    # Where the booking came from - lets admin tell walk-up trips a driver books on-site (no
    # customer login involved) apart from ones the customer created themselves online.
    source = models.CharField(max_length=20, choices=BookingSource.choices, default=BookingSource.ONLINE)
    # Lets a customer with no account (or who never logs in) open a no-login payment page for
    # this specific booking - shared with them directly by the driver.
    customer_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True, unique=True)

    customer_name = models.CharField(max_length=100)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True)

    pickup_location = models.CharField(max_length=200)
    dropoff_location = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()

    # Required for self-drive bookings only - the customer is the one driving, so we need
    # proof of a valid license and ID on file before handing over the vehicle.
    customer_license_number = models.CharField(max_length=50, blank=True)
    customer_license_document = models.FileField(
        upload_to='bookings/licenses/', blank=True, null=True,
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='Required for self-drive bookings',
    )
    customer_id_document = models.FileField(
        upload_to='bookings/ids/', blank=True, null=True,
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='National ID or passport copy, required for self-drive bookings',
    )

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    notes = models.TextField(blank=True)

    # Set once the assigned driver has acknowledged this booking on their dashboard. Purely
    # informational - doesn't gate confirmation/payment, just lets the driver keep track of
    # what they've actually seen. Driver-onsite bookings are self-acknowledged at creation
    # (the driver already knows about their own walk-up booking).
    driver_acknowledged_at = models.DateTimeField(null=True, blank=True)

    # Set once an online booking's driver-acknowledgment deadline passes with no acknowledgment
    # (see acknowledgment_deadline / payments.scheduler's automated escalation sweep) and staff
    # have been alerted - fires at most once per booking, so staff aren't re-emailed on every
    # scheduler tick once they've already been told.
    ack_escalated_at = models.DateTimeField(null=True, blank=True)

    # Driver-confirmed facts about the physical trip, separate from payment status - paying in
    # full doesn't mean the car has actually been handed over or returned yet (the balance is
    # only due "on or before pickup," so it can clear before the trip even starts). See
    # start_trip()/end_trip().
    trip_started_at = models.DateTimeField(null=True, blank=True)
    trip_ended_at = models.DateTimeField(null=True, blank=True)

    # Set when staff nudge the driver about this booking's outstanding balance - see
    # core.views.AdminBookingViewSet.remind_balance. Separate from Payment.last_reminded_at, which is about a
    # specific already-declared payment; this is about the booking simply not being fully paid
    # yet, whether or not anything has been declared.
    last_balance_reminder_at = models.DateTimeField(null=True, blank=True)

    # Set once a stuck payment/deposit issue on this booking has sat unresolved long enough that
    # the automated reminder sweep gives up on the driver and alerts staff directly instead (see
    # payments.services.escalate_stuck_bookings) - fires at most once per booking, so staff aren't
    # re-emailed on every scheduler tick once they've already been told.
    payment_escalated_at = models.DateTimeField(null=True, blank=True)

    # Set once (at mark_cancelled time) to whichever refund rule actually applied to this
    # specific cancellation - never re-derived afterwards, since a staff driver-fault override
    # can't be reconstructed later from driver_acknowledged_at alone. Needed so a late-arriving
    # payment (see _reconcile_refund_after_late_payment) bumps the refund by the same rule the
    # cancellation itself used, not a freshly re-computed one. None (treated as full refund) for
    # any booking cancelled before this field existed.
    cancellation_full_refund = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_name} - {self.vehicle} ({self.start_date} to {self.end_date})'

    def _apply_default_driver(self):
        """A with-driver booking defaults to the vehicle's own assigned driver if none was given -
        the public booking flow never lets a customer pick a driver directly (there's no such
        field on the form), so without this, every online with-driver booking would silently end
        up with no driver at all: no payout, no notification, nothing."""
        if (
            self.service_type == ServiceType.WITH_DRIVER
            and not self.driver_id
            and self.vehicle_id
            and self.vehicle.driver_id
        ):
            self.driver_id = self.vehicle.driver_id

    def clean(self):
        self._apply_default_driver()

        # Only enforced on brand-new bookings (no pk yet) - once a booking exists, its start
        # date shouldn't become invalid retroactively just because time passed while it sat
        # pending, or block an unrelated field update (e.g. a note) on an older booking.
        if self.pk is None and self.start_date and self.start_date < timezone.localdate():
            raise ValidationError('Start date cannot be in the past.')

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('End date cannot be before start date.')

        if self.service_type == ServiceType.SELF_DRIVE:
            if not self.vehicle.allow_self_drive:
                raise ValidationError(f'{self.vehicle.name} does not allow self-drive bookings.')
            if not self.customer_license_document:
                raise ValidationError('A driving license document is required for self-drive bookings.')
            if not self.customer_id_document:
                raise ValidationError('A national ID or passport copy is required for self-drive bookings.')

        if self.service_type == ServiceType.WITH_DRIVER:
            if not self.vehicle.allow_with_driver:
                raise ValidationError(f'{self.vehicle.name} does not allow bookings with a driver.')

        if not (self.vehicle_id and self.start_date and self.end_date):
            return

        conflicts = Booking.objects.filter(
            status__in=BLOCKING_BOOKING_STATUSES,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)

        if conflicts.filter(vehicle_id=self.vehicle_id).exists():
            raise ValidationError(
                f'{self.vehicle.name} is already booked for part of that date range. Please choose different dates.'
            )

        if self.driver_id and conflicts.filter(driver_id=self.driver_id).exists():
            raise ValidationError(
                f'{self.driver.full_name} is already assigned to another booking for part of that date range.'
            )

    @property
    def rental_days(self):
        return (self.end_date - self.start_date).days + 1

    def save(self, *args, **kwargs):
        # clean() (which also applies this) only ever runs against the throwaway validation
        # candidate the serializer builds - not the actual instance being persisted - so this
        # has to be re-applied here too for it to actually stick.
        self._apply_default_driver()
        if not self.total_amount:
            total = self.vehicle.price_per_day * self.rental_days
            if self.service_type == ServiceType.SELF_DRIVE:
                total = (total * (Decimal('100') + SELF_DRIVE_SURCHARGE_PERCENT) / Decimal('100')).quantize(Decimal('0.01'))
            self.total_amount = total
        super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        from payments.models import PaymentStatus

        total = self.payments.filter(status=PaymentStatus.SUCCESSFUL).aggregate(
            total=models.Sum('amount')
        )['total']
        return total or Decimal('0')

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    @property
    def deposit_amount(self):
        """The fixed target deposit (doesn't shrink as it gets paid off)."""
        return (self.total_amount * self.DEPOSIT_PERCENT / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def is_deposit_paid(self):
        return self.amount_paid >= self.deposit_amount

    @property
    def _has_payout_recipient(self):
        """Whether *someone* actually earns a cut of this with-driver booking - an individual
        driver-partner's own car (Vehicle.is_company_owned=False, no FleetPartner owner), or a
        FleetPartner-owned vehicle (regardless of who's assigned to drive it). A company-owned
        vehicle's assigned driver is an employee/operator, not an owner, so the full fare is
        SilverLake's - no payout at all."""
        if self.service_type != ServiceType.WITH_DRIVER or not self.vehicle_id:
            return False
        vehicle = self.vehicle
        if vehicle.owner_id:
            return True
        return not vehicle.is_company_owned and bool(self.driver_id)

    @property
    def _payout_fee_percent(self):
        """SilverLake's cut - the fixed platform rate for an individual driver-partner, or that
        specific FleetPartner's own negotiated rate. Zero (meaningless) when there's no payout
        recipient at all - callers should check _has_payout_recipient first, not rely on this
        alone, since a partner can legitimately negotiate a real 0% rate."""
        if not self._has_payout_recipient:
            return Decimal('0')
        return self.vehicle.owner.platform_fee_percent if self.vehicle.owner_id else self.PLATFORM_FEE_PERCENT

    @property
    def platform_fee_amount(self):
        """SilverLake's cut, taken from the payout - only meaningful when someone actually earns
        a cut of this booking (see _has_payout_recipient)."""
        if not self._has_payout_recipient:
            return Decimal('0')
        return (self.total_amount * self._payout_fee_percent / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def driver_payout_amount(self):
        """What's actually paid out, after the platform fee - to the driver-partner who owns the
        vehicle, or to the FleetPartner organization that does (see Booking._ensure_driver_payout
        for which). Zero unless someone earns a cut at all (see _has_payout_recipient) - note
        this can still be the full total_amount if a partner's own rate happens to be 0%."""
        if not self._has_payout_recipient:
            return Decimal('0')
        return self.total_amount - self.platform_fee_amount

    @property
    def needs_attention(self):
        """Past its scheduled end date but still open - either nobody ever confirmed it
        started/ended, or it ended but couldn't auto-complete because it still owes money.
        Purely a nudge for admins to look into it; nothing ever resolves this automatically -
        only a human confirming what actually happened (or chasing an unpaid balance) should
        close a trip out."""
        return (
            self.status in (BookingStatus.CONFIRMED, BookingStatus.ONGOING)
            and self.end_date < timezone.localdate()
        )

    @property
    def acknowledgment_deadline(self):
        """When the assigned driver needs to have acknowledged this booking by. Fixed at
        booking-creation time (same-day-ness is judged against created_at's own date, not
        whatever "today" happens to be whenever this property is later evaluated) - a same-day
        pickup gets ACKNOWLEDGMENT_DEADLINE_SAME_DAY, anything booked further ahead gets the
        more relaxed ACKNOWLEDGMENT_DEADLINE_FUTURE. Measured from created_at rather than
        start_date itself, since that's the only anchor that works the same way regardless of
        how far off the pickup date is."""
        placed_on = timezone.localtime(self.created_at).date()
        threshold = ACKNOWLEDGMENT_DEADLINE_SAME_DAY if self.start_date == placed_on else ACKNOWLEDGMENT_DEADLINE_FUTURE
        return self.created_at + threshold

    @property
    def is_acknowledgment_overdue(self):
        """True once an online booking's driver-acknowledgment deadline has passed with no
        acknowledgment yet - see payments.scheduler's automated escalation sweep, which alerts
        staff once this is true. Never true for a walk-in booking (self-acknowledged at
        creation - see DriverOnsiteBookingCreateView) or once the driver has actually started
        the trip (they've clearly already engaged with it, acknowledgment button or not)."""
        return (
            self.driver_id is not None
            and self.driver_acknowledged_at is None
            and self.trip_started_at is None
            and self.status not in (BookingStatus.CANCELLED, BookingStatus.COMPLETED)
            and timezone.now() > self.acknowledgment_deadline
        )

    @property
    def has_undeposited_cash(self):
        """True if any confirmed cash payment on this booking is still missing a matching
        Paybill deposit (see payments.services.log_cash_deposit) - the same gate
        AdminDriverPayoutViewSet.verify already enforces before a payout can be verified,
        reused here so a trip can't complete a step ahead of confirming SilverLake actually
        has the money, not just that the driver said the client paid them in cash."""
        from payments.models import PaymentMethod, PaymentStatus

        return self.payments.filter(
            method=PaymentMethod.CASH, status=PaymentStatus.SUCCESSFUL, cash_deposit__isnull=True,
        ).exists()

    def start_trip(self):
        """Driver-confirmed: the vehicle has actually been handed over. Only valid once the
        deposit has landed (CONFIRMED) - a customer can't be mid-trip on a booking that was
        never paid for."""
        if self.status != BookingStatus.CONFIRMED:
            raise ValidationError(f'Cannot start a trip that is {self.get_status_display().lower()}.')
        self.status = BookingStatus.ONGOING
        self.trip_started_at = timezone.now()
        self.save(update_fields=['status', 'trip_started_at'])

    def end_trip(self):
        """Driver-confirmed: the vehicle has been physically returned. If the booking happens
        to already be fully paid at this point, completes it immediately - this is the one
        place it's actually safe to treat "fully paid" as "trip is done", because a human has
        just confirmed the car is back, not just that money arrived (money can land before the
        trip even starts). If there's still a balance due, the trip stays open with
        trip_ended_at recorded, and _complete_if_ended_and_paid() finishes the job later once
        the balance clears (see confirm_if_deposit_met)."""
        if self.status not in (BookingStatus.CONFIRMED, BookingStatus.ONGOING):
            raise ValidationError(f'Cannot end a trip that is {self.get_status_display().lower()}.')
        if not self.trip_ended_at:
            self.trip_ended_at = timezone.now()
            self.save(update_fields=['trip_ended_at'])
        self._complete_if_ended_and_paid()

    def _complete_if_ended_and_paid(self):
        """The only safe place a payment alone is allowed to complete a booking: the driver has
        already confirmed via end_trip() that the car is physically back, so a payment clearing
        the balance after that point really does mean the trip is over - not just that the
        customer happened to pay early. Called from end_trip() (in case it was already fully
        paid) and from confirm_if_deposit_met() (in case the balance only clears after the trip
        already ended).

        Also withheld while any cash payment on this booking is still undeposited
        (has_undeposited_cash) - the customer has genuinely paid (balance_due already reflects
        that), but "trip completed" is also the signal that triggers the review-invite email and
        marks the whole affair settled, so it waits for the driver to actually hand the cash over
        to SilverLake too, not just the client's word that they paid the driver. Silently defers
        rather than erroring, matching how a nonzero balance_due already defers this the same way
        - see DriverBookingCompleteView/AdminBookingViewSet.set_status for the user-facing 400
        this produces when someone tries to force completion directly instead."""
        if self.status == BookingStatus.COMPLETED or not self.trip_ended_at or self.balance_due > 0:
            return
        if self.has_undeposited_cash:
            return
        self.status = BookingStatus.COMPLETED
        self.save(update_fields=['status'])

        from .emails import send_trip_completed_email

        send_trip_completed_email(self)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.TRIP_COMPLETED, f'Your trip #{self.pk} is complete - leave a review!',
            user=self.user, link_path='/account/bookings',
        )

    def confirm_if_deposit_met(self):
        """Confirms the booking once the deposit lands (pending -> confirmed, one-time). The
        driver's payout is handled separately in _ensure_driver_payout, which only queues once
        the booking is fully paid - not just deposited - so call this again on every later
        payment too (e.g. the customer clearing the remaining balance afterwards): the
        confirmation part is a no-op the second time, but the payout check isn't.

        The assigned driver is notified separately, at booking creation rather than here - see
        BookingViewSet.perform_create - so they find out as soon as a customer books them, not
        only once a deposit happens to land."""
        if self.status == BookingStatus.CANCELLED:
            # An M-Pesa payment that was already in flight before the booking got cancelled can
            # still land here via the callback - never queue a payout for a trip that isn't
            # happening, and make sure the refund actually covers what's arrived since.
            self._reconcile_refund_after_late_payment()
            return

        if self.status == BookingStatus.PENDING and self.is_deposit_paid:
            self.status = BookingStatus.CONFIRMED
            self.save(update_fields=['status'])
            self._send_confirmation_email()

            from notifications.models import NotificationEvent
            from notifications.services import notify

            notify(
                NotificationEvent.BOOKING_CONFIRMED, f'Your booking #{self.pk} for {self.vehicle.name} is confirmed',
                user=self.user, link_path='/account/bookings',
            )

        self._ensure_driver_payout()
        self._complete_if_ended_and_paid()

    def _owed_refund_amount(self):
        """The refund rule this specific cancellation used (see cancellation_full_refund) applied
        to whatever's actually been paid right now - shared by mark_cancelled (setting the
        refund for the first time) and _reconcile_refund_after_late_payment (a payment landing
        after cancellation has to be topped up by the same rule, not a freshly re-derived one)."""
        if self.cancellation_full_refund is False:
            return (self.amount_paid / Decimal('2')).quantize(Decimal('0.01'))
        return self.amount_paid

    def _reconcile_refund_after_late_payment(self):
        """A payment landing on an already-cancelled booking still needs to be accounted for -
        either bumps an existing pending Refund up to the real amount owed, or creates one if
        this is the first money that's shown up since cancellation. Never touches a refund
        that's already been issued - that's a manual reconciliation for admin at that point."""
        if self.amount_paid <= 0:
            return
        from payments.models import Refund, RefundStatus

        owed = self._owed_refund_amount()
        refund, created = Refund.objects.get_or_create(booking=self, defaults={'amount': owed})
        if not created and refund.status == RefundStatus.PENDING and refund.amount != owed:
            refund.amount = owed
            refund.save(update_fields=['amount'])

    def mark_cancelled(self, driver_at_fault=False):
        """Cancels the booking. If money had already been collected against it, this is the
        only place that flags it for a manual refund - there's no automated M-Pesa refund API
        wired up, so admin sends it back by hand and marks the Refund record issued once done.

        Refunds the full amount paid if the driver hadn't actually committed to the trip yet (no
        driver_acknowledged_at) or if staff attest the driver was at fault - went unavailable, or
        delayed without notice, through no fault of the client's (driver_at_fault=True; only
        staff should ever pass this, since a client cancelling themselves has no way to know why
        their driver went quiet). Otherwise - the client cancelling after the driver had already
        acknowledged and committed - only half the amount paid is refunded, since the driver's
        own time was already spent. Self-drive bookings have no driver-acknowledgment concept, so
        they always get a full refund.

        Also voids any driver payout that hadn't been paid out yet, since a cancelled trip
        shouldn't still owe the driver their cut."""
        if self.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
            raise ValidationError(f'Booking is already {self.get_status_display().lower()}.')

        full_refund = driver_at_fault or not self.driver_acknowledged_at
        self.status = BookingStatus.CANCELLED
        self.cancellation_full_refund = full_refund
        self.save(update_fields=['status', 'cancellation_full_refund'])

        if self.amount_paid > 0:
            from payments.models import Refund

            Refund.objects.get_or_create(booking=self, defaults={'amount': self._owed_refund_amount()})

        if hasattr(self, 'driver_payout') and not self.driver_payout.is_paid:
            self.driver_payout.void()

        from .emails import send_booking_cancelled_email

        send_booking_cancelled_email(self)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.BOOKING_CANCELLED, f'Booking #{self.pk} for {self.customer_name} was cancelled',
            organization=self.vehicle.owner, link_path='/admin/bookings',
        )
        if self.driver_id:
            notify(
                NotificationEvent.BOOKING_CANCELLED, f'Booking #{self.pk} for {self.customer_name} was cancelled',
                driver=self.driver, link_path='/driver',
            )
        notify(
            NotificationEvent.BOOKING_CANCELLED, f'Your booking #{self.pk} was cancelled',
            user=self.user, link_path='/account/bookings',
        )

    def _send_confirmation_email(self):
        """Sends a booking confirmed email to the customer. Swallowed silently on failure
        so a misconfigured SMTP server never blocks a successful booking."""
        try:
            from django.conf import settings
            from core.email_utils import send_branded_email

            service_label = 'Book with Driver' if self.service_type == ServiceType.WITH_DRIVER else 'Self Drive'
            send_branded_email(
                subject=f'Booking Confirmed — SilverLake Car Rentals #{self.pk}',
                template_name='emails/booking_confirmed.html',
                context={
                    'first_name': self.customer_name.split()[0],
                    'booking_id': self.pk,
                    'vehicle_name': self.vehicle.name,
                    'service_type': service_label,
                    'driver_name': self.driver.full_name if self.driver else None,
                    'start_date': self.start_date.strftime('%d %b %Y'),
                    'end_date': self.end_date.strftime('%d %b %Y'),
                    'pickup_location': self.pickup_location,
                    'total_amount': f'{self.total_amount:,.2f}',
                    'amount_paid': f'{self.amount_paid:,.2f}',
                    'balance_due': f'{self.balance_due:,.2f}',
                    'bookings_url': f'{settings.FRONTEND_URL}/account/bookings',
                },
                recipient_list=[self.customer_email] if self.customer_email else [],
            )
        except Exception:
            pass  # Never crash a booking over email

    def _ensure_driver_payout(self):
        """Records what's owed once the booking is fully paid - not merely deposited, since the
        payout is calculated on the whole trip value and shouldn't be queued while the business
        has only actually collected a fraction of that (e.g. just the 30% deposit). Owed to the
        driver-partner who owns the vehicle, or to the FleetPartner organization that does (see
        _has_payout_recipient) - money for either currently still lands in SilverLake's own
        Paybill regardless (no per-partner routing is wired up), so this is the same kind of "we
        owe you, staff disburse by hand" record either way. Doesn't pay anyone - staff mark
        DriverPayout.is_paid once the money has actually been sent out. If any of the payments
        behind this were self-reported cash or card (no independent gateway confirming either,
        unlike M-Pesa), the payout is flagged for admin to verify before it can be paid out."""
        if self.driver_payout_amount <= 0 or self.balance_due > 0:
            return
        from payments.models import DriverPayout, PaymentMethod, PaymentStatus

        has_offline_payment = self.payments.filter(
            status=PaymentStatus.SUCCESSFUL, method__in=(PaymentMethod.CASH, PaymentMethod.CARD),
        ).exists()

        defaults = {'amount': self.driver_payout_amount, 'needs_verification': has_offline_payment}
        if self.vehicle.owner_id:
            defaults['organization_id'] = self.vehicle.owner_id
        else:
            defaults['driver_id'] = self.driver_id

        DriverPayout.objects.get_or_create(booking=self, defaults=defaults)
