from django.db import models
from django.utils import timezone

from bookings.models import Booking
from drivers.models import Driver


class PaymentMethod(models.TextChoices):
    MPESA = 'mpesa', 'M-Pesa'
    CARD = 'card', 'Card'
    CASH = 'cash', 'Cash'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SUCCESSFUL = 'successful', 'Successful'
    FAILED = 'failed', 'Failed'


class Payment(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=15, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    # M-Pesa Daraja STK Push fields
    mpesa_checkout_request_id = models.CharField(max_length=100, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)

    # Card payment gateway reference (e.g. Flutterwave/Stripe transaction id)
    card_transaction_ref = models.CharField(max_length=100, blank=True)

    # Set for cash payments a driver reports on the spot (e.g. a walk-up client who paid cash
    # instead of via M-Pesa) - keeps an audit trail of who vouched for the money being received.
    recorded_by_driver = models.ForeignKey(
        Driver, null=True, blank=True, on_delete=models.SET_NULL, related_name='cash_payments_recorded',
    )
    note = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_method_display()} - {self.amount} ({self.status})'


class DriverPayout(models.Model):
    """What SilverLake owes a driver-partner for a with-driver booking, after the platform fee."""

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='driver_payout')
    # PROTECT, not CASCADE - deleting a driver shouldn't silently take their payout history
    # (paid or not) with them. A driver with payouts on file has to be suspended, not deleted.
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True, help_text='M-Pesa/bank reference used to pay the driver')
    notes = models.TextField(blank=True)

    # Set when the booking was confirmed off the back of a self-reported cash payment (no
    # independent gateway confirming it, unlike M-Pesa) - an admin must explicitly verify
    # before this payout can be marked paid, so a fabricated cash claim can't sail straight
    # through to a real payout.
    needs_verification = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    # Set when the booking behind this payout gets cancelled before the payout was disbursed -
    # a cancelled trip shouldn't still owe the driver their cut, but the record is kept (not
    # deleted) so there's a trail of what would have been paid.
    is_voided = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.driver.full_name} - KES {self.amount} ({"paid" if self.is_paid else "pending"})'

    def verify(self):
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'verified_at'])

    def mark_paid(self, reference=''):
        self.is_paid = True
        self.paid_at = timezone.now()
        if reference:
            self.payout_reference = reference
        self.save(update_fields=['is_paid', 'paid_at', 'payout_reference'])

        from .emails import send_payout_paid_email

        send_payout_paid_email(self)

    def void(self):
        self.is_voided = True
        self.voided_at = timezone.now()
        self.save(update_fields=['is_voided', 'voided_at'])


class RefundStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ISSUED = 'issued', 'Issued'


class Refund(models.Model):
    """Tracks money owed back to a customer after a cancelled booking. There's no automated
    M-Pesa refund API wired up, so this just gives admin a durable record of what's owed and
    a place to confirm once they've sent it back by hand."""

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='refund')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=15, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    reference = models.CharField(max_length=100, blank=True, help_text='M-Pesa/bank reference used to send the refund')
    notes = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Refund for booking #{self.booking_id} - KES {self.amount} ({self.status})'

    def mark_issued(self, reference=''):
        self.status = RefundStatus.ISSUED
        self.issued_at = timezone.now()
        if reference:
            self.reference = reference
        self.save(update_fields=['status', 'issued_at', 'reference'])

        from .emails import send_refund_issued_email

        send_refund_issued_email(self)
