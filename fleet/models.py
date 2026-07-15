from decimal import Decimal

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


class FleetPartner(models.Model):
    """A company (or eventually an individual) that has registered its own fleet with
    SilverLake - distinct from an individual driver-partner (drivers.Driver), since one
    FleetPartner can own many vehicles, possibly driven by different people who aren't
    necessarily the owner themselves. Deliberately holds no *inbound* payment details of its
    own - every client payment, for any vehicle regardless of ownership, goes through
    SilverLake's single Paybill (see MPESA_* settings), specifically so the platform fee is
    never at risk of not being collected (a partner's own Paybill/Daraja credentials were
    briefly added then deliberately removed - see fleet/migrations 0014/0015). payout_phone_number
    is the opposite direction - where SilverLake eventually sends this partner's own cut back
    out - and carries none of that inbound-collection risk. SilverLake keeps
    platform_fee_percent as revenue; the rest is owed back to the partner via the normal
    DriverPayout mechanism (organization set instead of driver) - see PLATFORM_OVERVIEW.md."""

    name = models.CharField(max_length=150)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    payout_phone_number = models.CharField(
        max_length=20, blank=True,
        help_text="M-Pesa number this partner's own share of a payout is sent to - kept "
                   "separate from contact_phone so a general contact number is never mistaken "
                   "for a real money destination.",
    )

    platform_fee_percent = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('10'),
        help_text="SilverLake's cut of this partner's bookings, owed back by the partner.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


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
    # or driver-submitted-vehicle flow. Company-owned fleet vehicles leave this blank - but see
    # is_company_owned below, since `driver` alone is also set for a company vehicle that just
    # has an employee assigned to drive it, which is a different case ownership-wise.
    driver = models.ForeignKey(
        'drivers.Driver', null=True, blank=True, on_delete=models.SET_NULL, related_name='vehicles',
    )

    # Set automatically to False by DriverApplication.approve()/VehicleSubmission.approve() - a
    # driver-partner's own submitted car is never company-owned. Defaults True for anything
    # admin adds directly via Admin -> Fleet. Drives whether a with-driver booking on this
    # vehicle creates a driver payout at all (see Booking.driver_payout_amount) - a company
    # vehicle's assigned driver is an employee/operator, not an owner, so there's no payout to
    # them; the full fare is SilverLake's. Existing vehicles created before this field existed
    # all default to True on migration and were NOT re-classified - if any of them are actually
    # driver-owned, that needs fixing by hand in Admin -> Fleet, since there's no reliable way to
    # infer it retroactively (both cases just had `driver` set, indistinguishably, until now).
    is_company_owned = models.BooleanField(
        default=True,
        help_text='Uncheck if this vehicle is owned by its assigned driver, not by SilverLake - '
                   'affects whether a with-driver booking on it creates a driver payout.',
    )
    # A registered fleet-owning company - a different ownership case from an individual
    # driver-partner (see FleetPartner docstring). Null means either company-owned
    # (is_company_owned=True) or an individual driver-partner's own car (is_company_owned=False,
    # owned by `driver` above) - mutually exclusive in practice, not enforced at the DB level.
    # PROTECT, not SET_NULL: losing this silently would make the vehicle indistinguishable from
    # an individually driver-owned one (both would read owner=None, is_company_owned=False),
    # misattributing payout economics - a partner with vehicles on file has to have those
    # reassigned first, not just get deleted out from under them.
    owner = models.ForeignKey(
        FleetPartner, null=True, blank=True, on_delete=models.PROTECT, related_name='vehicles',
    )

    # Last-known GPS position, reported by whichever driver has an active trip in this vehicle
    # (see bookings.views.DriverBookingLocationView) - not a location history, just the latest
    # fix, so admins can see roughly where a vehicle is right now on the fleet map.
    last_location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)

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

    # No mileage/odometer tracking anywhere in the app, so "due" is purely time-based off the
    # last logged VehicleServiceRecord - or off when the vehicle went live, if it's never been
    # serviced at all.
    SERVICE_DUE_INTERVAL_DAYS = 90

    @property
    def is_service_due(self):
        records = list(self.service_records.all())  # ordered -service_date, uses prefetch cache if present
        baseline = records[0].service_date if records else self.created_at.date()
        return (timezone.now().date() - baseline).days >= self.SERVICE_DUE_INTERVAL_DAYS


def visible_vehicles():
    """Vehicles whose /fleet/<id> detail page actually resolves right now, applying the exact
    same exclusions as VehicleViewSet.get_queryset() (currently booked, lapsed insurance/
    inspection, driver away/suspended) - shared so the two can never drift apart, since the
    sitemap in particular must never link to a URL that 404s. Imports bookings.models lazily to
    avoid a circular import (bookings.models imports fleet.models at module level)."""
    from datetime import date

    from bookings.models import BLOCKING_BOOKING_STATUSES, Booking

    today = date.today()
    currently_booked_ids = Booking.objects.filter(
        status__in=BLOCKING_BOOKING_STATUSES,
        start_date__lte=today,
        end_date__gte=today,
    ).values_list('vehicle_id', flat=True)

    return (
        Vehicle.objects.filter(is_available=True)
        .exclude(id__in=currently_booked_ids)
        .exclude(insurance_expiry_date__lt=today)
        .exclude(inspection_expiry_date__lt=today)
        .exclude(driver__is_away=True)
        .exclude(driver__is_active=False)
    )


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


class VehicleServiceRecord(models.Model):
    """A logged service/maintenance event for a vehicle - a running history, not just a single
    'last serviced' date, so admins can see everything ever done to a vehicle. A driver-partner
    logs these for their own vehicle from the Driver Portal; admins can log one for any vehicle
    (e.g. company-owned fleet cars, which have no owning driver to log it themselves)."""

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='service_records')
    service_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True, help_text='e.g. "Oil change + filter"')
    # Null if logged by an admin rather than a driver-partner.
    logged_by = models.ForeignKey(
        'drivers.Driver', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-service_date', '-created_at']

    def __str__(self):
        return f'{self.vehicle.name} serviced {self.service_date}'


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
            is_company_owned=False,
        )
        for photo in photos[1:]:
            VehicleImage.objects.create(vehicle=self.created_vehicle, image=photo.image, order=photo.order)

        self.status = VehicleSubmissionStatus.APPROVED
        self.reviewed_at = timezone.now()
        self.save()

        from drivers.emails import send_vehicle_submission_approved_email

        send_vehicle_submission_approved_email(self)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.VEHICLE_SUBMISSION_APPROVED, f'Your {self.name} submission is now live',
            driver=self.driver, link_path='/driver',
        )

    def reject(self, notes=''):
        self.status = VehicleSubmissionStatus.REJECTED
        if notes:
            self.review_notes = notes
        self.reviewed_at = timezone.now()
        self.save()

        from drivers.emails import send_vehicle_submission_rejected_email

        send_vehicle_submission_rejected_email(self)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.VEHICLE_SUBMISSION_REJECTED, f'Your {self.name} submission was not approved',
            driver=self.driver, link_path='/driver',
        )


class VehicleSubmissionPhoto(models.Model):
    """One of at least two photos a driver must provide when submitting a car for review."""

    submission = models.ForeignKey(VehicleSubmission, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='vehicle_submissions/photos/', validators=[validate_file_size])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.submission.name} photo #{self.pk}'
