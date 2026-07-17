from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from core.images import optimize_image
from fleet.models import VehicleCategory

from .validators import validate_file_size

DOCUMENT_EXTENSIONS = FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])


class Driver(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='driver_profile', help_text='Login account for the driver portal, if one has been set up.',
    )
    full_name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='drivers/', blank=True, null=True)
    email = models.EmailField(blank=True, help_text='Used to notify the driver when they get booked')
    phone_number = models.CharField(max_length=20, blank=True)
    years_of_experience = models.PositiveSmallIntegerField(default=0)
    bio = models.TextField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.0)
    is_active = models.BooleanField(default=True)

    # Superadmin-controlled, not the driver's own choice - opt-in, not opt-out: a newly
    # registered driver can't accept cash at all until a superadmin explicitly turns it on for
    # them, since cash is the one payment method this app can't independently verify (see
    # PAYMENT_SECURITY.md). Enforced in payments.services.declare_offline_payment, the single
    # entry point both the driver's own "declare payment" action and a customer's no-login
    # self-declare page go through. Default=False only affects newly created drivers - existing
    # ones aren't retroactively changed (confirmed with the user 2026-07-14).
    cash_payments_enabled = models.BooleanField(default=False)

    # Self-reported unavailability (e.g. sick, on leave) - distinct from is_active (admin
    # suspension). Either one hides the driver's vehicles from the public fleet listing.
    is_away = models.BooleanField(default=False)
    away_reason = models.TextField(blank=True, help_text='Visible to admins only, not customers.')

    # Set by admin when suspending (is_active=False); emailed to the driver so they know why.
    suspension_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if self.photo and not self.photo._committed:
            optimize_image(self.photo, max_dimension=800)
        super().save(*args, **kwargs)

    def recalculate_rating(self):
        """Recomputes this driver's displayed rating from their approved reviews. Called
        whenever a review tied to this driver is approved, rejected, or deleted - without this,
        `rating` would just sit at its default forever, showing every driver as a flat 5.0
        regardless of what customers actually said."""
        from django.db.models import Avg

        average = self.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))['avg']
        self.rating = round(average, 2) if average is not None else Decimal('5.0')
        self.save(update_fields=['rating'])


class ApplicationStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class DriverApplication(models.Model):
    """A public 'become a driver' submission - the driver and their car only go live once
    an admin approves it, at which point real Driver/Vehicle records are created."""

    # Applicant
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    years_of_experience = models.PositiveSmallIntegerField(default=0)
    bio = models.TextField(blank=True)
    license_number = models.CharField(max_length=50)
    license_document = models.FileField(
        upload_to='driver_applications/licenses/',
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='Photo or PDF of your driving license, max 5MB',
    )

    # The car they want enlisted alongside them
    vehicle_name = models.CharField(max_length=100)
    vehicle_category = models.ForeignKey(
        VehicleCategory, on_delete=models.PROTECT, related_name='driver_applications',
    )
    passenger_capacity = models.PositiveSmallIntegerField()
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    vehicle_photo = models.ImageField(
        upload_to='driver_applications/vehicles/', blank=True, null=True,
        validators=[validate_file_size],
    )
    vehicle_logbook_document = models.FileField(
        upload_to='driver_applications/logbooks/', blank=True, null=True,
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='Proof of vehicle ownership/registration, max 5MB',
    )

    status = models.CharField(max_length=10, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING)
    review_notes = models.TextField(blank=True)
    created_driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_vehicle = models.ForeignKey(
        'fleet.Vehicle', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.status})'

    def save(self, *args, **kwargs):
        # license_document/vehicle_logbook_document are deliberately untouched - compliance
        # documents need to stay full-fidelity and legible, unlike a marketing/listing photo.
        if self.vehicle_photo and not self.vehicle_photo._committed:
            optimize_image(self.vehicle_photo)
        super().save(*args, **kwargs)

    def approve(self):
        from fleet.models import Vehicle

        if self.status == ApplicationStatus.APPROVED:
            return

        self.created_driver = Driver.objects.create(
            full_name=self.full_name,
            email=self.email,
            phone_number=self.phone_number,
            years_of_experience=self.years_of_experience,
            bio=self.bio,
            is_active=True,
        )
        self.created_vehicle = Vehicle.objects.create(
            name=self.vehicle_name,
            category=self.vehicle_category,
            passenger_capacity=self.passenger_capacity,
            price_per_day=self.price_per_day,
            image=self.vehicle_photo or None,
            is_available=True,
            driver=self.created_driver,
            is_company_owned=False,
        )
        self.status = ApplicationStatus.APPROVED
        self.reviewed_at = timezone.now()
        self.save()

        from .services import create_driver_login

        create_driver_login(self.created_driver)

    def reject(self, notes=''):
        self.status = ApplicationStatus.REJECTED
        if notes:
            self.review_notes = notes
        self.reviewed_at = timezone.now()
        self.save()

        from .emails import send_driver_application_rejected_email

        send_driver_application_rejected_email(self)
