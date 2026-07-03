from django.db import models
from django.utils import timezone

from bookings.models import Booking
from drivers.models import Driver


class PaymentMethod(models.TextChoices):
    MPESA = 'mpesa', 'M-Pesa'
    CARD = 'card', 'Card'


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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_method_display()} - {self.amount} ({self.status})'


class DriverPayout(models.Model):
    """What SilverLake owes a driver-partner for a with-driver booking, after the platform fee."""

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='driver_payout')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True, help_text='M-Pesa/bank reference used to pay the driver')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.driver.full_name} - KES {self.amount} ({"paid" if self.is_paid else "pending"})'

    def mark_paid(self, reference=''):
        self.is_paid = True
        self.paid_at = timezone.now()
        if reference:
            self.payout_reference = reference
        self.save(update_fields=['is_paid', 'paid_at', 'payout_reference'])
