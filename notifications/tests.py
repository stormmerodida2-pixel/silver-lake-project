from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from core.models import StaffOrganization
from drivers.models import Driver
from fleet.models import FleetPartner

from .models import NotificationEvent, NotificationPreference, PushSubscription
from .push import _recipients_for
from .services import notify

FAKE_VAPID = override_settings(VAPID_PRIVATE_KEY='fake-private-key', VAPID_PUBLIC_KEY='fake-public-key')

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


class NotificationPreferenceTests(APITestCase):
    """Muting an event type hides it from that one user's own feed only - never from anyone
    else who'd otherwise see the exact same underlying Notification (e.g. two admins in the
    same organization). Checked at read time (get_queryset), not inside notify() itself."""

    def setUp(self):
        self.org_a = FleetPartner.objects.create(name='Pref Org A', platform_fee_percent=Decimal('10'))
        self.org_a_staff_1 = User.objects.create_user(username='pref-org-a-1@example.com', password='pass12345!', is_staff=True)
        StaffOrganization.objects.create(user=self.org_a_staff_1, organization=self.org_a)
        self.org_a_staff_2 = User.objects.create_user(username='pref-org-a-2@example.com', password='pass12345!', is_staff=True)
        StaffOrganization.objects.create(user=self.org_a_staff_2, organization=self.org_a)

        self.booking_notification = notify(NotificationEvent.BOOKING_CREATED, 'New booking', organization=self.org_a)
        self.dispute_notification = notify(NotificationEvent.PAYMENT_DISPUTED, 'Disputed', organization=self.org_a)

    def test_muting_an_event_hides_it_from_the_list(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        response = self.client.get('/api/admin/notifications/')
        events = {n['event'] for n in response.json()['results']}
        self.assertEqual(events, {NotificationEvent.PAYMENT_DISPUTED})

    def test_muting_does_not_affect_another_user_in_the_same_organization(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        self.client.force_authenticate(user=self.org_a_staff_2)
        response = self.client.get('/api/admin/notifications/')
        events = {n['event'] for n in response.json()['results']}
        self.assertEqual(events, {NotificationEvent.BOOKING_CREATED, NotificationEvent.PAYMENT_DISPUTED})

    def test_unmuting_restores_it(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')
        self.client.post('/api/admin/notifications/unmute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        response = self.client.get('/api/admin/notifications/')
        events = {n['event'] for n in response.json()['results']}
        self.assertEqual(events, {NotificationEvent.BOOKING_CREATED, NotificationEvent.PAYMENT_DISPUTED})

    def test_muting_twice_does_not_error(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        first = self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')
        second = self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')
        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)

    def test_muting_an_invalid_event_is_rejected(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        response = self.client.post('/api/admin/notifications/mute/', {'event': 'not_a_real_event'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_preferences_endpoint_lists_muted_events(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        response = self.client.get('/api/admin/notifications/preferences/')
        self.assertEqual(response.json()['muted_events'], [NotificationEvent.BOOKING_CREATED])

    def test_muted_event_also_excluded_from_unread_count(self):
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        response = self.client.get('/api/admin/notifications/unread-count/')
        self.assertEqual(response.json()['count'], 1)  # only the still-unmuted dispute notification

    def test_preferences_are_shared_across_all_three_feeds(self):
        # The same account's own mute preference applies no matter which URL prefix (admin/
        # driver/client) they hit - it's the same underlying per-user table either way.
        self.client.force_authenticate(user=self.org_a_staff_1)
        self.client.post('/api/admin/notifications/mute/', {'event': NotificationEvent.BOOKING_CREATED}, format='json')

        response = self.client.get('/api/notifications/preferences/')
        self.assertEqual(response.json()['muted_events'], [NotificationEvent.BOOKING_CREATED])


class PushRecipientResolutionTests(TestCase):
    """_recipients_for mirrors exactly what each NotificationViewSet.get_queryset already
    computes for the in-app bell - see NotificationViewSetTests above for the same org-scoping
    rules being exercised there."""

    def setUp(self):
        self.platform_staff = User.objects.create_user(username='push-platform@example.com', password='x', is_staff=True)
        self.org = FleetPartner.objects.create(name='Push Org', platform_fee_percent=Decimal('10'))
        self.org_staff = User.objects.create_user(username='push-org-staff@example.com', password='x', is_staff=True)
        StaffOrganization.objects.create(user=self.org_staff, organization=self.org)
        self.other_org_staff = User.objects.create_user(username='push-other-org-staff@example.com', password='x', is_staff=True)
        StaffOrganization.objects.create(
            user=self.other_org_staff, organization=FleetPartner.objects.create(name='Push Org 2', platform_fee_percent=Decimal('10')),
        )
        self.plain_user = User.objects.create_user(username='push-plain@example.com', password='x')
        self.driver_user = User.objects.create_user(username='push-driver@example.com', password='x')
        self.driver = Driver.objects.create(user=self.driver_user, full_name='Push Driver', is_active=True)

    def test_user_scoped_notification_resolves_to_that_user_only(self):
        notification = notify(NotificationEvent.BOOKING_CONFIRMED, 'x', user=self.plain_user)
        self.assertEqual(list(_recipients_for(notification)), [self.plain_user])

    def test_driver_scoped_notification_resolves_to_that_drivers_own_account(self):
        notification = notify(NotificationEvent.DRIVER_BOOKED, 'x', driver=self.driver)
        self.assertEqual(list(_recipients_for(notification)), [self.driver_user])

    def test_platform_wide_notification_resolves_to_platform_staff_only(self):
        notification = notify(NotificationEvent.DRIVER_APPLICATION, 'x')
        recipients = set(_recipients_for(notification))
        self.assertIn(self.platform_staff, recipients)
        self.assertNotIn(self.org_staff, recipients)

    def test_org_scoped_notification_resolves_to_that_orgs_staff_and_platform_staff(self):
        notification = notify(NotificationEvent.BOOKING_CREATED, 'x', organization=self.org)
        recipients = set(_recipients_for(notification))
        self.assertIn(self.org_staff, recipients)
        self.assertIn(self.platform_staff, recipients)
        self.assertNotIn(self.other_org_staff, recipients)


@FAKE_VAPID
class SendPushNotificationsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='push-send@example.com', password='x')
        self.subscription = PushSubscription.objects.create(
            user=self.user, endpoint='https://push.example.com/abc', p256dh='p256dh-key', auth='auth-key',
        )

    @patch('notifications.push.webpush')
    def test_sends_to_a_subscribed_recipient(self, mock_webpush):
        notify(NotificationEvent.BOOKING_CONFIRMED, 'Your booking is confirmed', user=self.user)
        mock_webpush.assert_called_once()
        call_kwargs = mock_webpush.call_args.kwargs
        self.assertEqual(call_kwargs['subscription_info']['endpoint'], self.subscription.endpoint)

    @patch('notifications.push.webpush')
    def test_muted_event_is_not_pushed(self, mock_webpush):
        NotificationPreference.objects.create(user=self.user, event=NotificationEvent.BOOKING_CONFIRMED)
        notify(NotificationEvent.BOOKING_CONFIRMED, 'Your booking is confirmed', user=self.user)
        mock_webpush.assert_not_called()

    @patch('notifications.push.webpush')
    def test_a_user_with_no_subscription_is_silently_skipped(self, mock_webpush):
        other_user = User.objects.create_user(username='push-no-sub@example.com', password='x')
        notify(NotificationEvent.BOOKING_CONFIRMED, 'x', user=other_user)
        mock_webpush.assert_not_called()

    @override_settings(VAPID_PRIVATE_KEY='')
    @patch('notifications.push.webpush')
    def test_no_op_when_vapid_is_not_configured(self, mock_webpush):
        notify(NotificationEvent.BOOKING_CONFIRMED, 'x', user=self.user)
        mock_webpush.assert_not_called()

    @patch('notifications.push.webpush')
    def test_a_dead_subscription_is_deleted_on_410(self, mock_webpush):
        from pywebpush import WebPushException

        class FakeResponse:
            status_code = 410

        mock_webpush.side_effect = WebPushException('gone', response=FakeResponse())
        notify(NotificationEvent.BOOKING_CONFIRMED, 'x', user=self.user)
        self.assertFalse(PushSubscription.objects.filter(pk=self.subscription.pk).exists())

    @patch('notifications.push.webpush')
    def test_a_transient_failure_does_not_delete_the_subscription(self, mock_webpush):
        from pywebpush import WebPushException

        class FakeResponse:
            status_code = 500

        mock_webpush.side_effect = WebPushException('server error', response=FakeResponse())
        notify(NotificationEvent.BOOKING_CONFIRMED, 'x', user=self.user)
        self.assertTrue(PushSubscription.objects.filter(pk=self.subscription.pk).exists())


class PushSubscriptionAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='push-api@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.user)

    def test_can_subscribe(self):
        response = self.client.post('/api/push/subscription/', {
            'endpoint': 'https://push.example.com/xyz',
            'keys': {'p256dh': 'p', 'auth': 'a'},
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(PushSubscription.objects.filter(user=self.user, endpoint='https://push.example.com/xyz').exists())

    def test_missing_keys_rejected(self):
        response = self.client.post('/api/push/subscription/', {'endpoint': 'https://push.example.com/xyz'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_can_unsubscribe(self):
        PushSubscription.objects.create(user=self.user, endpoint='https://push.example.com/xyz', p256dh='p', auth='a')
        response = self.client.delete('/api/push/subscription/', {'endpoint': 'https://push.example.com/xyz'}, format='json')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PushSubscription.objects.exists())

    def test_anonymous_cannot_subscribe(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/push/subscription/', {
            'endpoint': 'https://push.example.com/xyz', 'keys': {'p256dh': 'p', 'auth': 'a'},
        }, format='json')
        self.assertIn(response.status_code, (401, 403))

    @FAKE_VAPID
    def test_vapid_public_key_endpoint_returns_the_configured_key(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/push/vapid-public-key/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['public_key'], 'fake-public-key')
