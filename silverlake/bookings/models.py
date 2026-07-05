import uuid
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
    driver_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)

    # Where the booking came from - lets admin tell walk-up trips a driver books on-site (no
    # customer login involved) apart from ones the customer created themselves online.
    source = models.CharField(max_length=20, choices=BookingSource.choices, default=BookingSource.ONLINE)
    # Lets a customer with no account (or who never logs in) open a no-login payment page for
    # this specific booking - shared with them directly by the driver, distinct from driver_token.
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_name} - {self.vehicle} ({self.start_date} to {self.end_date})'

    def clean(self):
        # Only enforced on brand-new bookings (no pk yet) - once a booking exists, its start
        # date shouldn't become invalid retroactively just because time passed while it sat
        # pending, or block an unrelated field update (e.g. a note) on an older booking.
        if self.pk is None and self.start_date and self.start_date < timezone.now().date():
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
        if not self.total_amount:
            self.total_amount = self.vehicle.price_per_day * self.rental_days
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
    def platform_fee_amount(self):
        """SilverLake's cut, taken from the driver's payout on with-driver bookings only."""
        if self.service_type != ServiceType.WITH_DRIVER or not self.driver_id:
            return Decimal('0')
        return (self.total_amount * self.PLATFORM_FEE_PERCENT / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def driver_payout_amount(self):
        """What the assigned driver is actually paid out, after the platform fee."""
        if self.service_type != ServiceType.WITH_DRIVER or not self.driver_id:
            return Decimal('0')
        return self.total_amount - self.platform_fee_amount

    def confirm_if_deposit_met(self):
        """Confirms the booking once the deposit lands (pending -> confirmed, one-time). The
        driver's payout is handled separately in _ensure_driver_payout, which only queues once
        the booking is fully paid - not just deposited - so call this again on every later
        payment too (e.g. the customer clearing the remaining balance afterwards): the
        confirmation part is a no-op the second time, but the payout check isn't.

        The assigned driver is notified separately, at booking creation rather than here - see
        BookingViewSet.perform_create - so they find out as soon as a customer books them, not
        only once a deposit happens to land."""
        if self.status == BookingStatus.PENDING and self.is_deposit_paid:
            self.status = BookingStatus.CONFIRMED
            self.save(update_fields=['status'])
            self._send_confirmation_email()

        self._ensure_driver_payout()

    def mark_cancelled(self):
        """Cancels the booking. If money had already been collected against it, this is the
        only place that flags it for a manual refund - there's no automated M-Pesa refund API
        wired up, so admin sends it back by hand and marks the Refund record issued once done.
        Also voids any driver payout that hadn't been paid out yet, since a cancelled trip
        shouldn't still owe the driver their cut."""
        if self.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
            raise ValidationError(f'Booking is already {self.get_status_display().lower()}.')

        self.status = BookingStatus.CANCELLED
        self.save(update_fields=['status'])

        if self.amount_paid > 0:
            from payments.models import Refund

            Refund.objects.get_or_create(booking=self, defaults={'amount': self.amount_paid})

        if hasattr(self, 'driver_payout') and not self.driver_payout.is_paid:
            self.driver_payout.void()

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
        """Records what's owed to the driver once the booking is fully paid - not merely
        deposited, since the driver's cut is calculated on the whole trip value and shouldn't
        be queued for payout while the business has only actually collected a fraction of that
        (e.g. just the 30% deposit). Doesn't pay them - staff mark DriverPayout.is_paid once the
        money has actually been disbursed. If any of the payments behind this were self-reported
        cash (no independent gateway confirming it, unlike M-Pesa), the payout is flagged for
        admin to verify before it can be paid out."""
        if self.driver_payout_amount <= 0 or self.balance_due > 0:
            return
        from payments.models import DriverPayout, PaymentMethod, PaymentStatus

        has_cash_payment = self.payments.filter(status=PaymentStatus.SUCCESSFUL, method=PaymentMethod.CASH).exists()

        DriverPayout.objects.get_or_create(
            booking=self,
            defaults={
                'driver_id': self.driver_id,
                'amount': self.driver_payout_amount,
                'needs_verification': has_cash_payment,
            },
        )
