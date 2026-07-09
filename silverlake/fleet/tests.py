from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from bookings.models import Booking, BookingStatus, ServiceType
from drivers.models import Driver

from .models import Vehicle, VehicleCategory

User = get_user_model()

TODAY = date.today()


def make_vehicle(**kwargs):
    if 'category' not in kwargs:
        kwargs['category'], _ = VehicleCategory.objects.get_or_create(
            slug='compact_sedan', defaults={'name': 'Compact Sedan'},
        )
    defaults = dict(
        name='Test Car', passenger_capacity=4,
        price_per_day=Decimal('1000'), is_available=True,
    )
    defaults.update(kwargs)
    return Vehicle.objects.create(**defaults)


class PublicFleetVisibilityTests(APITestCase):
    """/api/vehicles/ should only ever show vehicles a customer can actually book right now."""

    def test_unavailable_vehicle_is_hidden(self):
        make_vehicle(name='Hidden', is_available=False)
        self.assertNotIn('Hidden', self._names_on_public_list())

    def test_vehicle_with_lapsed_insurance_is_hidden(self):
        make_vehicle(name='Lapsed Insurance', insurance_expiry_date=TODAY - timedelta(days=1))
        self.assertNotIn('Lapsed Insurance', self._names_on_public_list())

    def test_vehicle_with_no_insurance_date_recorded_is_still_shown(self):
        make_vehicle(name='No Insurance Date')
        self.assertIn('No Insurance Date', self._names_on_public_list())

    def test_vehicle_with_lapsed_inspection_is_hidden(self):
        make_vehicle(name='Lapsed Inspection', inspection_expiry_date=TODAY - timedelta(days=1))
        self.assertNotIn('Lapsed Inspection', self._names_on_public_list())

    def test_vehicle_currently_booked_is_hidden(self):
        vehicle = make_vehicle(name='Currently Booked')
        user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        Booking.objects.create(
            user=user, vehicle=vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TODAY - timedelta(days=1), end_date=TODAY + timedelta(days=1),
            status=BookingStatus.CONFIRMED,
        )
        self.assertNotIn('Currently Booked', self._names_on_public_list())

    def test_vehicle_with_no_driver_is_unaffected_by_driver_status(self):
        make_vehicle(name='Company Car', driver=None)
        self.assertIn('Company Car', self._names_on_public_list())

    def test_vehicle_hidden_while_its_driver_is_marked_away(self):
        driver = Driver.objects.create(full_name='Away Driver', is_active=True, is_away=True)
        make_vehicle(name='Away Driver Car', driver=driver)
        self.assertNotIn('Away Driver Car', self._names_on_public_list())

    def test_vehicle_hidden_while_its_driver_is_suspended(self):
        driver = Driver.objects.create(full_name='Suspended Driver', is_active=False)
        make_vehicle(name='Suspended Driver Car', driver=driver)
        self.assertNotIn('Suspended Driver Car', self._names_on_public_list())

    def test_vehicle_visible_when_its_driver_is_active_and_available(self):
        driver = Driver.objects.create(full_name='Good Driver', is_active=True, is_away=False)
        make_vehicle(name='Good Driver Car', driver=driver)
        self.assertIn('Good Driver Car', self._names_on_public_list())

    def _names_on_public_list(self):
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        return [v['name'] for v in results]


class PublicCategoryApiTests(APITestCase):
    """Fleet types are managed on the admin dashboard, but everyone needs to read them -
    the public fleet page's filters and the driver/become-a-driver forms all depend on this
    being reachable with no login."""

    def test_categories_are_publicly_listed_ordered_by_order_then_name(self):
        VehicleCategory.objects.create(name='Zebra Van', order=99)
        VehicleCategory.objects.create(name='Alpha Sedan', order=99)
        response = self.client.get('/api/categories/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        names = [c['name'] for c in results]
        self.assertEqual(names[-2:], ['Alpha Sedan', 'Zebra Van'])

    def test_category_slug_is_auto_generated_from_name(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.assertEqual(category.slug, 'luxury-convertible')

    def test_vehicles_can_be_filtered_by_category_slug(self):
        sedan = VehicleCategory.objects.create(name='Sedan')
        van = VehicleCategory.objects.create(name='Van')
        make_vehicle(name='A Sedan Car', category=sedan)
        make_vehicle(name='A Van', category=van)
        response = self.client.get('/api/vehicles/', {'category': 'sedan'})
        names = [v['name'] for v in response.json().get('results', response.json())]
        self.assertEqual(names, ['A Sedan Car'])

    def test_retired_categories_are_not_publicly_listed(self):
        VehicleCategory.objects.create(name='Retired Type', is_active=False)
        response = self.client.get('/api/categories/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        names = [c['name'] for c in results]
        self.assertNotIn('Retired Type', names)

    def test_a_vehicle_using_a_retired_category_still_shows_up_and_names_it_correctly(self):
        retired = VehicleCategory.objects.create(name='Retired Type', is_active=False)
        make_vehicle(name='Legacy Car', category=retired)
        response = self.client.get('/api/vehicles/')
        results = response.json().get('results', response.json())
        legacy = next(v for v in results if v['name'] == 'Legacy Car')
        self.assertEqual(legacy['category_name'], 'Retired Type')
