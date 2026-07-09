from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .validators import validate_file_size

DOCUMENT_EXTENSIONS = FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])


class VehicleCategory(models.Model):
    """A fleet type (e.g. Executive SUV). Admin-managed so new categories can be added from
    the dashboard instead of requiring a code change - used to be a fixed enum."""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text='Lower numbers show first')
    is_active = models.BooleanField(
        default=True,
        help_text='Uncheck to stop offering this type for new vehicles/applications, without '
                   'deleting it or affecting vehicles that already use it.',
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'vehicle categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Vehicle(models.Model):
    name = models.CharField(max_length=100, help_text='e.g. Toyota Prado TZG')
    category = models.ForeignKey(VehicleCategory, on_delete=models.PROTECT, related_name='vehicles')
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

    # The driver-partner who owns/drives this car, if it came from the driver-onboarding
    # or driver-submitted-vehicle flow. Company-owned fleet vehicles leave this blank.
    driver = models.ForeignKey(
        'drivers.Driver', null=True, blank=True, on_delete=models.SET_NULL, related_name='vehicles',
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


class VehicleSubmissionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class VehicleSubmission(models.Model):
    """A car a driver-partner has added themselves via the driver portal - stays pending
    until an admin approves it, at which point a real Vehicle record is created."""

    driver = models.ForeignKey('drivers.Driver', on_delete=models.CASCADE, related_name='vehicle_submissions')

    name = models.CharField(max_length=100)
    category = models.ForeignKey(VehicleCategory, on_delete=models.PROTECT, related_name='vehicle_submissions')
    tagline = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    passenger_capacity = models.PositiveSmallIntegerField()
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    logbook_document = models.FileField(
        upload_to='vehicle_submissions/logbooks/',
        validators=[DOCUMENT_EXTENSIONS, validate_file_size],
        help_text='Proof of ownership/registration, max 5MB',
    )

    status = models.CharField(max_length=10, choices=VehicleSubmissionStatus.choices, default=VehicleSubmissionStatus.PENDING)
    review_notes = models.TextField(blank=True)
    created_vehicle = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.driver.full_name}, {self.status})'

    def approve(self):
        if self.status == VehicleSubmissionStatus.APPROVED:
            return

        photos = list(self.photos.all())
        self.created_vehicle = Vehicle.objects.create(
            name=self.name,
            category=self.category,
            tagline=self.tagline,
            description=self.description,
            passenger_capacity=self.passenger_capacity,
            price_per_day=self.price_per_day,
            image=photos[0].image if photos else None,
            is_available=True,
            allow_self_drive=False,
            allow_with_driver=True,
            driver=self.driver,
        )
        for photo in photos[1:]:
            VehicleImage.objects.create(vehicle=self.created_vehicle, image=photo.image, order=photo.order)

        self.status = VehicleSubmissionStatus.APPROVED
        self.reviewed_at = timezone.now()
        self.save()

    def reject(self, notes=''):
        self.status = VehicleSubmissionStatus.REJECTED
        if notes:
            self.review_notes = notes
        self.reviewed_at = timezone.now()
        self.save()


class VehicleSubmissionPhoto(models.Model):
    """One of at least two photos a driver must provide when submitting a car for review."""

    submission = models.ForeignKey(VehicleSubmission, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='vehicle_submissions/photos/', validators=[validate_file_size])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.submission.name} photo #{self.pk}'
