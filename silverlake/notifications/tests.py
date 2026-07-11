from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import StaffOrganization
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
