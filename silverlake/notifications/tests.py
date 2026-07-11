from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import StaffOrganization
from drivers.models import Driver
from fleet.models import FleetPartner

from .models import Notification, NotificationEvent
from .services import notify

User = get_user_model()


class NotifyServiceTests(TestCase):
    def test_notify_creates_a_notification(self):
        org = FleetPartner.objects.create(name='Notify Org', platform_fee_percent=Decimal('10'))
        notification = notify(
            NotificationEvent.BOOKING_CREATED, 'Test message', organization=org, link_path='/admin/bookings',
        )
        self.assertEqual(notification.event, NotificationEvent.BOOKING_CREATED)
        self.assertEqual(notification.message, 'Test message')
        self.assertEqual(notification.organization_id, org.id)
        self.assertEqual(notification.link_path, '/admin/bookings')

    def test_notify_defaults_to_platform_wide(self):
        notification = notify(NotificationEvent.DRIVER_AWAY, 'Test')
        self.assertIsNone(notification.organization_id)
        self.assertEqual(notification.link_path, '')

    def test_notify_can_target_a_specific_driver(self):
        driver = Driver.objects.create(full_name='Notify Target Driver', is_active=True)
        notification = notify(NotificationEvent.DRIVER_BOOKED, 'You were booked', driver=driver, link_path='/driver')
        self.assertEqual(notification.driver_id, driver.id)
        self.assertIsNone(notification.organization_id)

    def test_notify_can_target_a_specific_client(self):
        user = User.objects.create_user(username='notify-target-client@example.com', password='pass12345!')
        notification = notify(
            NotificationEvent.BOOKING_CONFIRMED, 'Your booking is confirmed', user=user, link_path='/account/bookings',
        )
        self.assertEqual(notification.user_id, user.id)
        self.assertIsNone(notification.organization_id)
        self.assertIsNone(notification.driver_id)


class NotificationViewSetTests(APITestCase):
    """Org-scoping follows the exact same convention as every other admin resource (see
    core.permissions.get_user_organization) - a platform account sees everything, an org-scoped
    account only sees its own organization's notifications, and platform-only events
    (organization=None) are invisible to an org-scoped account, same as Fleet Partners or the
    Activity Log."""

    def setUp(self):
        self.platform_staff = User.objects.create_user(
            username='notif-platform@example.com', password='pass12345!', is_staff=True,
        )

        self.org_a = FleetPartner.objects.create(name='Notif Org A', platform_fee_percent=Decimal('10'))
        self.org_a_staff = User.objects.create_user(username='notif-org-a@example.com', password='pass12345!', is_staff=True)
        StaffOrganization.objects.create(user=self.org_a_staff, organization=self.org_a)

        self.org_b = FleetPartner.objects.create(name='Notif Org B', platform_fee_percent=Decimal('10'))

        self.plain_user = User.objects.create_user(username='notif-plain@example.com', password='pass12345!')

        self.org_a_notification = notify(NotificationEvent.BOOKING_CREATED, 'Org A booking', organization=self.org_a)
        self.org_b_notification = notify(NotificationEvent.BOOKING_CREATED, 'Org B booking', organization=self.org_b)
        self.platform_notification = notify(NotificationEvent.DRIVER_APPLICATION, 'New application')

    def test_platform_staff_sees_everything(self):
        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/notifications/')
        ids = {n['id'] for n in response.json()['results']}
        self.assertEqual(ids, {self.org_a_notification.id, self.org_b_notification.id, self.platform_notification.id})

    def test_org_admin_only_sees_their_own_orgs_notifications(self):
        self.client.force_authenticate(user=self.org_a_staff)
        response = self.client.get('/api/admin/notifications/')
        ids = {n['id'] for n in response.json()['results']}
        self.assertEqual(ids, {self.org_a_notification.id})

    def test_non_staff_cannot_view_notifications(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.get('/api/admin/notifications/')
        self.assertEqual(response.status_code, 403)

    def test_unread_count_is_scoped_the_same_way(self):
        self.client.force_authenticate(user=self.org_a_staff)
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)

    def test_platform_staffs_unread_count_includes_everything(self):
        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 3)

    def test_marking_read_reduces_unread_count(self):
        self.client.force_authenticate(user=self.platform_staff)
        self.client.post(f'/api/admin/notifications/{self.org_a_notification.id}/mark-read/')
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 2)

    def test_mark_read_is_per_user_not_global(self):
        self.client.force_authenticate(user=self.platform_staff)
        self.client.post(f'/api/admin/notifications/{self.org_a_notification.id}/mark-read/')

        other_staff = User.objects.create_user(username='notif-other-staff@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=other_staff)
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 3)

    def test_mark_all_read_clears_unread_count(self):
        self.client.force_authenticate(user=self.platform_staff)
        self.client.post('/api/admin/notifications/mark-all-read/')
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 0)

    def test_mark_all_read_does_not_affect_another_org(self):
        self.client.force_authenticate(user=self.org_a_staff)
        self.client.post('/api/admin/notifications/mark-all-read/')

        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 3)  # platform staff's own read state is untouched

    def test_org_admin_cannot_mark_another_orgs_notification_read(self):
        self.client.force_authenticate(user=self.org_a_staff)
        response = self.client.post(f'/api/admin/notifications/{self.org_b_notification.id}/mark-read/')
        self.assertEqual(response.status_code, 404)

    def test_is_read_flag_reflects_mark_read(self):
        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/notifications/')
        item = next(n for n in response.json()['results'] if n['id'] == self.org_a_notification.id)
        self.assertFalse(item['is_read'])

        self.client.post(f'/api/admin/notifications/{self.org_a_notification.id}/mark-read/')
        response = self.client.get('/api/admin/notifications/')
        item = next(n for n in response.json()['results'] if n['id'] == self.org_a_notification.id)
        self.assertTrue(item['is_read'])


class DriverNotificationViewSetTests(APITestCase):
    """The driver portal's own notification feed - scoped to exactly the requesting driver,
    never another driver's, and never mixed up with the admin dashboard's own feed."""

    def setUp(self):
        self.driver_a_user = User.objects.create_user(username='drivernotif-a@example.com', password='pass12345!')
        self.driver_a = Driver.objects.create(user=self.driver_a_user, full_name='Notif Driver A', is_active=True)

        self.driver_b_user = User.objects.create_user(username='drivernotif-b@example.com', password='pass12345!')
        self.driver_b = Driver.objects.create(user=self.driver_b_user, full_name='Notif Driver B', is_active=True)

        self.plain_user = User.objects.create_user(username='drivernotif-plain@example.com', password='pass12345!')

        self.driver_a_notification = notify(NotificationEvent.DRIVER_BOOKED, 'A booked', driver=self.driver_a)
        self.driver_b_notification = notify(NotificationEvent.DRIVER_BOOKED, 'B booked', driver=self.driver_b)
        # An admin-facing notification with no driver at all - must never leak into a driver's feed.
        self.admin_notification = notify(NotificationEvent.BOOKING_CREATED, 'Admin only')

    def test_driver_only_sees_their_own_notifications(self):
        self.client.force_authenticate(user=self.driver_a_user)
        response = self.client.get('/api/driver/notifications/')
        ids = {n['id'] for n in response.json()['results']}
        self.assertEqual(ids, {self.driver_a_notification.id})

    def test_non_driver_cannot_view_driver_notifications(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.get('/api/driver/notifications/')
        self.assertEqual(response.status_code, 403)

    def test_driver_cannot_mark_another_drivers_notification_read(self):
        self.client.force_authenticate(user=self.driver_a_user)
        response = self.client.post(f'/api/driver/notifications/{self.driver_b_notification.id}/mark-read/')
        self.assertEqual(response.status_code, 404)

    def test_driver_unread_count_excludes_other_drivers_and_admin_notifications(self):
        self.client.force_authenticate(user=self.driver_a_user)
        response = self.client.get('/api/driver/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)

    def test_driver_mark_all_read_does_not_affect_another_driver(self):
        self.client.force_authenticate(user=self.driver_a_user)
        self.client.post('/api/driver/notifications/mark-all-read/')

        self.client.force_authenticate(user=self.driver_b_user)
        response = self.client.get('/api/driver/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)


class ClientNotificationViewSetTests(APITestCase):
    """A logged-in customer's own in-app event feed - booking confirmed/cancelled, a payment
    recorded, a trip completed, a refund issued. Scoped to exactly the requesting account, never
    another customer's, never the admin dashboard's or a driver's."""

    def setUp(self):
        self.client_a = User.objects.create_user(username='clientnotif-a@example.com', password='pass12345!')
        self.client_b = User.objects.create_user(username='clientnotif-b@example.com', password='pass12345!')

        self.client_a_notification = notify(NotificationEvent.BOOKING_CONFIRMED, 'A confirmed', user=self.client_a)
        self.client_b_notification = notify(NotificationEvent.BOOKING_CONFIRMED, 'B confirmed', user=self.client_b)
        # Admin- and driver-facing notifications with no user at all - must never leak into a
        # client's own feed.
        self.admin_notification = notify(NotificationEvent.BOOKING_CREATED, 'Admin only')

    def test_client_only_sees_their_own_notifications(self):
        self.client.force_authenticate(user=self.client_a)
        response = self.client.get('/api/notifications/')
        ids = {n['id'] for n in response.json()['results']}
        self.assertEqual(ids, {self.client_a_notification.id})

    def test_unauthenticated_user_cannot_view_notifications(self):
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 401)

    def test_client_cannot_mark_another_clients_notification_read(self):
        self.client.force_authenticate(user=self.client_a)
        response = self.client.post(f'/api/notifications/{self.client_b_notification.id}/mark-read/')
        self.assertEqual(response.status_code, 404)

    def test_client_unread_count_excludes_other_clients_and_admin_notifications(self):
        self.client.force_authenticate(user=self.client_a)
        response = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)

    def test_client_mark_all_read_does_not_affect_another_client(self):
        self.client.force_authenticate(user=self.client_a)
        self.client.post('/api/notifications/mark-all-read/')

        self.client.force_authenticate(user=self.client_b)
        response = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)
