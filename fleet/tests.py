from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking, BookingStatus, ServiceType, WaitlistEntry
from drivers.models import Driver

from .models import FavoriteVehicle, FleetPartner, Vehicle, VehicleCategory, VehicleServiceRecord

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


class VehicleServiceDueTests(APITestCase):
    """is_service_due is purely time-based (no mileage/odometer tracking exists anywhere) -
    due once it's been Vehicle.SERVICE_DUE_INTERVAL_DAYS since the last logged service, or
    since the vehicle went live if it's never been serviced at all."""

    def test_freshly_created_vehicle_with_no_service_history_is_not_yet_due(self):
        vehicle = make_vehicle()
        self.assertFalse(vehicle.is_service_due)

    def test_vehicle_never_serviced_becomes_due_after_the_interval_since_creation(self):
        vehicle = make_vehicle()
        old_created_at = timezone.now() - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 1)
        Vehicle.objects.filter(pk=vehicle.pk).update(created_at=old_created_at)
        vehicle.refresh_from_db()
        self.assertTrue(vehicle.is_service_due)

    def test_recently_serviced_vehicle_is_not_due(self):
        vehicle = make_vehicle()
        VehicleServiceRecord.objects.create(vehicle=vehicle, service_date=TODAY - timedelta(days=5))
        self.assertFalse(vehicle.is_service_due)

    def test_vehicle_serviced_long_ago_is_due_even_if_created_recently(self):
        vehicle = make_vehicle()
        VehicleServiceRecord.objects.create(
            vehicle=vehicle, service_date=TODAY - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 1),
        )
        self.assertTrue(vehicle.is_service_due)

    def test_most_recent_of_multiple_service_records_is_used(self):
        vehicle = make_vehicle()
        VehicleServiceRecord.objects.create(
            vehicle=vehicle, service_date=TODAY - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 30),
        )
        VehicleServiceRecord.objects.create(vehicle=vehicle, service_date=TODAY - timedelta(days=2))
        self.assertFalse(vehicle.is_service_due)


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


class PublicFleetTripsCompletedTests(APITestCase):
    """trips_completed is real social proof (see VehicleSerializer.get_trips_completed) - a
    genuine count of this vehicle's completed trips, not a fabricated urgency number."""

    def _trips_completed_for(self, vehicle_name):
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        return next(v['trips_completed'] for v in results if v['name'] == vehicle_name)

    def _make_booking(self, vehicle, status, user):
        return Booking.objects.create(
            user=user, vehicle=vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TODAY - timedelta(days=10), end_date=TODAY - timedelta(days=8),
            status=status,
        )

    def test_vehicle_with_no_bookings_shows_zero(self):
        make_vehicle(name='Untested Car')
        self.assertEqual(self._trips_completed_for('Untested Car'), 0)

    def test_only_completed_bookings_are_counted(self):
        vehicle = make_vehicle(name='Popular Car')
        user = User.objects.create_user(username='trips-client@example.com', password='pass12345!')
        self._make_booking(vehicle, BookingStatus.COMPLETED, user)
        self._make_booking(vehicle, BookingStatus.COMPLETED, user)
        self._make_booking(vehicle, BookingStatus.CANCELLED, user)
        self._make_booking(vehicle, BookingStatus.PENDING, user)
        self.assertEqual(self._trips_completed_for('Popular Car'), 2)


class VehicleAvailabilityTests(APITestCase):
    """/api/vehicles/<id>/availability/ lets the booking form warn about a date conflict before
    the customer submits - must mirror Booking.clean()'s own overlap window exactly, or it'd
    show dates as free that the server would then reject (or vice versa)."""

    def setUp(self):
        self.vehicle = make_vehicle(name='Available Car')
        self.user = User.objects.create_user(username='avail-client@example.com', password='pass12345!')

    def _make_booking(self, status, start_date, end_date):
        return Booking.objects.create(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=start_date, end_date=end_date, status=status,
        )

    def test_vehicle_with_no_bookings_has_no_blocked_ranges(self):
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_confirmed_future_booking_is_listed(self):
        self._make_booking(BookingStatus.CONFIRMED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['start_date'], str(TODAY + timedelta(days=5)))
        self.assertEqual(response.json()[0]['end_date'], str(TODAY + timedelta(days=7)))

    def test_pending_and_ongoing_bookings_are_also_listed(self):
        self._make_booking(BookingStatus.PENDING, TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        self._make_booking(BookingStatus.ONGOING, TODAY, TODAY + timedelta(days=1))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(len(response.json()), 2)

    def test_cancelled_booking_is_not_listed(self):
        self._make_booking(BookingStatus.CANCELLED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.json(), [])

    def test_completed_booking_is_not_listed(self):
        self._make_booking(BookingStatus.COMPLETED, TODAY - timedelta(days=5), TODAY - timedelta(days=3))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.json(), [])

    def test_a_booking_that_already_ended_is_not_listed(self):
        # An old CONFIRMED booking that never got marked completed shouldn't still block dates.
        self._make_booking(BookingStatus.CONFIRMED, TODAY - timedelta(days=10), TODAY - timedelta(days=8))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.json(), [])

    def test_another_vehicles_bookings_are_not_included(self):
        other_vehicle = make_vehicle(name='Other Car')
        Booking.objects.create(
            user=self.user, vehicle=other_vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TODAY + timedelta(days=5), end_date=TODAY + timedelta(days=7),
            status=BookingStatus.CONFIRMED,
        )
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.json(), [])

    def test_unauthenticated_request_is_allowed(self):
        self._make_booking(BookingStatus.CONFIRMED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        response = self.client.get(f'/api/vehicles/{self.vehicle.id}/availability/')
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_vehicle_404s(self):
        response = self.client.get('/api/vehicles/999999/availability/')
        self.assertEqual(response.status_code, 404)


class DateRangeFleetSearchTests(APITestCase):
    """?start_date=&end_date= on /api/vehicles/ powers date-first search on the Fleet page -
    only vehicles free for the whole requested range should come back. Must use the exact same
    overlap window as Booking.clean() and the availability action, or a vehicle shown as
    available here could still get rejected on actual booking."""

    def setUp(self):
        self.user = User.objects.create_user(username='search-client@example.com', password='pass12345!')

    def _make_booking(self, vehicle, status, start_date, end_date):
        return Booking.objects.create(
            user=self.user, vehicle=vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=start_date, end_date=end_date, status=status,
        )

    def _names_for(self, start_date, end_date):
        response = self.client.get('/api/vehicles/', {'start_date': start_date, 'end_date': end_date})
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        return [v['name'] for v in results]

    def test_vehicle_with_no_bookings_is_shown(self):
        make_vehicle(name='Free Car')
        self.assertIn('Free Car', self._names_for(TODAY + timedelta(days=5), TODAY + timedelta(days=7)))

    def test_vehicle_with_an_overlapping_confirmed_booking_is_excluded(self):
        vehicle = make_vehicle(name='Booked Car')
        self._make_booking(vehicle, BookingStatus.CONFIRMED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        self.assertNotIn('Booked Car', self._names_for(TODAY + timedelta(days=6), TODAY + timedelta(days=8)))

    def test_vehicle_with_a_non_overlapping_booking_is_shown(self):
        vehicle = make_vehicle(name='Later Car')
        self._make_booking(vehicle, BookingStatus.CONFIRMED, TODAY + timedelta(days=20), TODAY + timedelta(days=22))
        self.assertIn('Later Car', self._names_for(TODAY + timedelta(days=5), TODAY + timedelta(days=7)))

    def test_vehicle_with_only_a_cancelled_booking_in_range_is_shown(self):
        vehicle = make_vehicle(name='Reopened Car')
        self._make_booking(vehicle, BookingStatus.CANCELLED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        self.assertIn('Reopened Car', self._names_for(TODAY + timedelta(days=5), TODAY + timedelta(days=7)))

    def test_no_date_params_returns_everything_unfiltered(self):
        vehicle = make_vehicle(name='Booked Car No Filter')
        self._make_booking(vehicle, BookingStatus.CONFIRMED, TODAY + timedelta(days=5), TODAY + timedelta(days=7))
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        self.assertIn('Booked Car No Filter', [v['name'] for v in results])

    def test_end_date_before_start_date_is_ignored_not_a_500(self):
        make_vehicle(name='Backwards Range Car')
        response = self.client.get(
            '/api/vehicles/', {'start_date': str(TODAY + timedelta(days=7)), 'end_date': str(TODAY + timedelta(days=5))},
        )
        self.assertEqual(response.status_code, 200)

    def test_malformed_dates_are_ignored_not_a_500(self):
        make_vehicle(name='Malformed Range Car')
        response = self.client.get('/api/vehicles/', {'start_date': 'not-a-date', 'end_date': 'also-not-a-date'})
        self.assertEqual(response.status_code, 200)


class FavoriteVehicleTests(APITestCase):
    """Favoriting is a pure browsing convenience - no effect on booking, availability, or
    pricing - so these tests only cover the toggle/list mechanics themselves."""

    def setUp(self):
        self.vehicle = make_vehicle(name='Favorite Car')
        self.user = User.objects.create_user(username='fav-client@example.com', password='pass12345!')

    def test_vehicle_list_shows_is_favorited_false_by_default(self):
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        vehicle_data = next(v for v in results if v['name'] == 'Favorite Car')
        self.assertFalse(vehicle_data['is_favorited'])

    def test_anonymous_request_never_sees_is_favorited_true(self):
        FavoriteVehicle.objects.create(user=self.user, vehicle=self.vehicle)
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        vehicle_data = next(v for v in results if v['name'] == 'Favorite Car')
        self.assertFalse(vehicle_data['is_favorited'])

    def test_toggle_favorite_requires_login(self):
        response = self.client.post(f'/api/vehicles/{self.vehicle.id}/toggle_favorite/')
        self.assertEqual(response.status_code, 401)

    def test_toggle_favorite_creates_then_removes(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(f'/api/vehicles/{self.vehicle.id}/toggle_favorite/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_favorited'])
        self.assertTrue(FavoriteVehicle.objects.filter(user=self.user, vehicle=self.vehicle).exists())

        response = self.client.post(f'/api/vehicles/{self.vehicle.id}/toggle_favorite/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_favorited'])
        self.assertFalse(FavoriteVehicle.objects.filter(user=self.user, vehicle=self.vehicle).exists())


    def test_authenticated_vehicle_list_reflects_their_own_favorite(self):
        FavoriteVehicle.objects.create(user=self.user, vehicle=self.vehicle)
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/vehicles/')
        data = response.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        vehicle_data = next(v for v in results if v['name'] == 'Favorite Car')
        self.assertTrue(vehicle_data['is_favorited'])

    def test_favorites_list_requires_login(self):
        response = self.client.get('/api/vehicles/favorites/')
        self.assertEqual(response.status_code, 401)

    def test_favorites_list_only_returns_this_users_favorites(self):
        other_user = User.objects.create_user(username='other-fav@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='Someone Elses Favorite')
        FavoriteVehicle.objects.create(user=self.user, vehicle=self.vehicle)
        FavoriteVehicle.objects.create(user=other_user, vehicle=other_vehicle)

        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/vehicles/favorites/')
        names = [v['name'] for v in response.json()]
        self.assertIn('Favorite Car', names)
        self.assertNotIn('Someone Elses Favorite', names)

    def test_favoriting_the_same_vehicle_twice_does_not_duplicate(self):
        FavoriteVehicle.objects.create(user=self.user, vehicle=self.vehicle)
        with self.assertRaises(Exception):
            FavoriteVehicle.objects.create(user=self.user, vehicle=self.vehicle)


class VehicleWaitlistTests(APITestCase):
    """Joining the waitlist only makes sense when the requested dates are actually blocked by
    another booking - see bookings.services.notify_waitlist_for_freed_dates for the other half
    (getting told once they free up)."""

    def setUp(self):
        self.vehicle = make_vehicle(name='Waitlist Car')
        self.other_user = User.objects.create_user(username='owner@example.com', password='pass12345!')
        self.user = User.objects.create_user(username='waiter@example.com', password='pass12345!')
        self.start = TODAY + timedelta(days=10)
        self.end = TODAY + timedelta(days=15)
        Booking.objects.create(
            user=self.other_user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Someone Else', customer_phone='254700000001', pickup_location='Kisumu',
            start_date=self.start, end_date=self.end, status=BookingStatus.CONFIRMED,
        )
        self.client.force_authenticate(user=self.user)

    def test_joining_the_waitlist_requires_login(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f'/api/vehicles/{self.vehicle.id}/waitlist/',
            {'start_date': str(self.start), 'end_date': str(self.end)},
        )
        self.assertEqual(response.status_code, 401)

    def test_joining_the_waitlist_for_dates_that_actually_conflict_succeeds(self):
        response = self.client.post(
            f'/api/vehicles/{self.vehicle.id}/waitlist/',
            {'start_date': str(self.start), 'end_date': str(self.end)},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            WaitlistEntry.objects.filter(vehicle=self.vehicle, user=self.user, start_date=self.start, end_date=self.end).exists()
        )

    def test_joining_the_waitlist_for_dates_that_are_actually_free_is_rejected(self):
        free_start = self.end + timedelta(days=30)
        free_end = free_start + timedelta(days=3)
        response = self.client.post(
            f'/api/vehicles/{self.vehicle.id}/waitlist/',
            {'start_date': str(free_start), 'end_date': str(free_end)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WaitlistEntry.objects.filter(vehicle=self.vehicle, user=self.user).exists())

    def test_joining_twice_for_the_same_range_does_not_duplicate(self):
        payload = {'start_date': str(self.start), 'end_date': str(self.end)}
        self.client.post(f'/api/vehicles/{self.vehicle.id}/waitlist/', payload)
        self.client.post(f'/api/vehicles/{self.vehicle.id}/waitlist/', payload)
        self.assertEqual(WaitlistEntry.objects.filter(vehicle=self.vehicle, user=self.user).count(), 1)

    def test_invalid_dates_are_rejected(self):
        response = self.client.post(
            f'/api/vehicles/{self.vehicle.id}/waitlist/',
            {'start_date': str(self.end), 'end_date': str(self.start)},
        )
        self.assertEqual(response.status_code, 400)

    def test_leaving_the_waitlist_removes_the_entry(self):
        payload = {'start_date': str(self.start), 'end_date': str(self.end)}
        self.client.post(f'/api/vehicles/{self.vehicle.id}/waitlist/', payload)
        response = self.client.delete(f'/api/vehicles/{self.vehicle.id}/waitlist/', payload)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WaitlistEntry.objects.filter(vehicle=self.vehicle, user=self.user).exists())

    def test_my_waitlist_only_shows_the_current_users_own_entries(self):
        WaitlistEntry.objects.create(vehicle=self.vehicle, user=self.user, start_date=self.start, end_date=self.end)
        WaitlistEntry.objects.create(
            vehicle=self.vehicle, user=self.other_user, start_date=self.start, end_date=self.end,
        )
        response = self.client.get('/api/vehicles/waitlist/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['vehicle'], self.vehicle.id)


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


class AdminFleetPartnerTests(APITestCase):
    """Superadmin-only CRUD for registered fleet-owning companies - holds their platform fee
    rate (which only a genuine SilverLake superadmin can ever set, not even their own org-admin),
    so unlike most admin list endpoints, even viewing is restricted (not opened to regular
    support staff). Deliberately holds no *inbound* payment details of its own - every client
    payment goes through SilverLake's single Paybill regardless of vehicle ownership -
    payout_phone_number is the opposite direction (where the partner's own cut is eventually
    sent back out) and carries none of that inbound-collection risk."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='partner-super@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='partner-staff@example.com', password='pass12345!', is_staff=True)

    def test_superadmin_can_register_a_partner(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/fleet-partners/', {
            'name': 'Coastline Rentals Ltd', 'contact_email': 'ops@coastline.co.ke',
            'platform_fee_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        partner = FleetPartner.objects.get()
        self.assertEqual(partner.name, 'Coastline Rentals Ltd')
        self.assertEqual(partner.platform_fee_percent, Decimal('10'))

    def test_payout_phone_number_can_be_set_separately_from_contact_phone(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/fleet-partners/', {
            'name': 'Coastline Rentals Ltd', 'contact_phone': '254700111222',
            'payout_phone_number': '254711333444', 'platform_fee_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        partner = FleetPartner.objects.get()
        self.assertEqual(partner.contact_phone, '254700111222')
        self.assertEqual(partner.payout_phone_number, '254711333444')

    def test_support_staff_cannot_view_or_create_partners(self):
        self.client.force_authenticate(user=self.staff)
        list_response = self.client.get('/api/admin/fleet-partners/')
        self.assertEqual(list_response.status_code, 403)
        create_response = self.client.post('/api/admin/fleet-partners/', {'name': 'X'}, format='json')
        self.assertEqual(create_response.status_code, 403)

    def test_deleting_a_partner_with_a_vehicle_is_blocked(self):
        partner = FleetPartner.objects.create(name='Has A Car')
        make_vehicle(name='Partner Car', owner=partner, is_company_owned=False)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-partners/{partner.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(FleetPartner.objects.filter(id=partner.id).exists())

    def test_deleting_a_partner_with_no_vehicles_succeeds(self):
        partner = FleetPartner.objects.create(name='No Cars Yet')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-partners/{partner.id}/')
        self.assertEqual(response.status_code, 204)

    def test_vehicle_count_reflects_assigned_vehicles(self):
        partner = FleetPartner.objects.create(name='Counted Co')
        make_vehicle(name='Car One', owner=partner, is_company_owned=False)
        make_vehicle(name='Car Two', owner=partner, is_company_owned=False)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(f'/api/admin/fleet-partners/{partner.id}/')
        self.assertEqual(response.json()['vehicle_count'], 2)
