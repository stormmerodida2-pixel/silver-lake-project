from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import CustomerProfile
from fleet.models import Vehicle, VehicleCategory

User = get_user_model()

# Fixed, well-known credentials - never used against a real database. This command refuses to
# run unless DEBUG is on (see handle()), so there's no path for these to end up live.
E2E_CUSTOMER_EMAIL = 'e2e.customer@example.com'
E2E_ADMIN_EMAIL = 'e2e.admin@example.com'
E2E_PASSWORD = 'E2eTest123!'
E2E_VEHICLE_NAME = 'E2E Test Vehicle'


class Command(BaseCommand):
    help = (
        "Seeds a fixed customer account, a fixed superadmin account, and one bookable vehicle "
        "with known, predictable credentials - for the Playwright e2e suite (frontend/e2e/) to "
        "log in against. Skips real account activation entirely (accounts are created already "
        "active) since e2e tests exercise the booking/admin flows, not email delivery - that's "
        "already covered by the backend test suite. Refuses to run outside DEBUG so these fixed "
        "passwords can never land in a real database. Idempotent - safe to re-run."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('seed_e2e_data refuses to run with DEBUG=False - never run this against production.')

        customer, created = User.objects.get_or_create(
            username=E2E_CUSTOMER_EMAIL,
            defaults={
                'email': E2E_CUSTOMER_EMAIL, 'first_name': 'E2E', 'last_name': 'Customer', 'is_active': True,
            },
        )
        customer.set_password(E2E_PASSWORD)
        customer.save()
        CustomerProfile.objects.get_or_create(user=customer, defaults={'phone_number': '254700000000'})
        self.stdout.write(f'{"Created" if created else "Updated"}: customer "{E2E_CUSTOMER_EMAIL}"')

        admin, created = User.objects.get_or_create(
            username=E2E_ADMIN_EMAIL,
            defaults={
                'email': E2E_ADMIN_EMAIL, 'first_name': 'E2E', 'last_name': 'Admin',
                'is_active': True, 'is_staff': True, 'is_superuser': True,
            },
        )
        admin.set_password(E2E_PASSWORD)
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(f'{"Created" if created else "Updated"}: superadmin "{E2E_ADMIN_EMAIL}"')

        future_date = timezone.localdate().replace(year=timezone.localdate().year + 2)
        vehicle, created = Vehicle.objects.get_or_create(
            name=E2E_VEHICLE_NAME,
            defaults={
                'category': VehicleCategory.objects.get(slug='compact_sedan'),
                'passenger_capacity': 4,
                'tagline': 'Reserved for automated end-to-end tests',
                'price_per_day': Decimal('5000'),
                'description': 'A dedicated vehicle used only by the Playwright e2e suite - not part of the real fleet.',
                'is_available': True,
                'allow_self_drive': True,
                'allow_with_driver': True,
                'insurance_expiry_date': future_date,
                'inspection_expiry_date': future_date,
            },
        )
        self.stdout.write(f'{"Created" if created else "Already exists"}: vehicle "{vehicle.name}"')

        self.stdout.write(self.style.SUCCESS(
            f'E2E fixtures ready. Customer/Admin password for both accounts: {E2E_PASSWORD}'
        ))
