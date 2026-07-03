from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from .validators import validate_file_size

DOCUMENT_EXTENSIONS = FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])


class VehicleCategory(models.TextChoices):
    EXECUTIVE_SUV = 'executive_suv', 'Executive SUV'
    PREMIUM_MPV = 'premium_mpv', 'Premium MPV'
    COMPACT_SEDAN = 'compact_sedan', 'Compact Sedan'
    PASSENGER_VAN = 'passenger_van', 'Passenger Van'


class Vehicle(models.Model):
    name = models.CharField(max_length=100, help_text='e.g. Toyota Prado TZG')
    category = models.CharField(max_length=20, choices=VehicleCategory.choices)
    tagline = models.CharField(max_length=150, blank=True, help_text='e.g. Luxury - Power - Prestige')
    passenger_capacity = models.PositiveSmallIntegerField()
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='fleet/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    allow_self_drive = models.BooleanField(default=True)
    allow_with_driver = models.BooleanField(default=True)

    insurance_provider = models.CharField(max_length=100, blank=True)
    insurance_policy_number = models.CharField(max_length=50, blank=True)
    insurance_expiry_date = models.DateField(null=True, blank=True)
    insurance_document = models.FileField(
        upload_to='fleet/insurance/', blank=True, null=True,
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='Insurance certificate, max 5MB',
    )
    inspection_expiry_date = models.DateField(
        null=True, blank=True, help_text='NTSA inspection sticker expiry',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_insurance_expired(self):
        return bool(self.insurance_expiry_date and self.insurance_expiry_date < timezone.now().date())

    @property
    def is_inspection_expired(self):
        return bool(self.inspection_expiry_date and self.inspection_expiry_date < timezone.now().date())


class VehicleImage(models.Model):
    """Additional gallery photos for a vehicle, beyond its primary `image`."""

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='fleet/gallery/')
    caption = models.CharField(max_length=150, blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text='Lower numbers show first')

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.vehicle.name} photo #{self.pk}'
