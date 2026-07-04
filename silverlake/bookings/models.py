import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

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


# Bookings in these statuses hold the vehicle; cancelled/completed ones don't block dates.
BLOCKING_BOOKING_STATUSES = [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.ONGOING]


class Booking(models.Model):
    DEPOSIT_PERCENT = Decimal('30')
    # SilverLake's cut of a with-driver booking; the rest is paid out to the assigned driver.
    # Self-drive bookings have no driver payout, so the platform keeps the full amount either way.
    PLATFORM_FEE_PERCENT = Decimal('15')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='bookings')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    driver_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_name} - {self.vehicle} ({self.start_date} to {self.end_date})'

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('End date cannot be before start date.')

        if self.service_type == ServiceType.SELF_DRIVE:
            if not self.customer_license_document:
                raise ValidationError('A driving license document is required for self-drive bookings.')
            if not self.customer_id_document:
                raise ValidationError('A national ID or passport copy is required for self-drive bookings.')

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
        if self.status == BookingStatus.PENDING and self.is_deposit_paid:
            self.status = BookingStatus.CONFIRMED
            self.save(update_fields=['status'])
            self._ensure_driver_payout()
            self._send_confirmation_email()
            if self.driver_id:
                from .emails import send_driver_booking_notification

                send_driver_booking_notification(self)

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
        """Records what's owed to the driver once their booking is confirmed. Doesn't pay them -
        staff mark DriverPayout.is_paid once the money has actually been disbursed."""
        if self.driver_payout_amount <= 0:
            return
        from payments.models import DriverPayout

        DriverPayout.objects.get_or_create(
            booking=self,
            defaults={'driver_id': self.driver_id, 'amount': self.driver_payout_amount},
        )
