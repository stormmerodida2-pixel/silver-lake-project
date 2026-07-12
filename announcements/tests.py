from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from drivers.models import Driver

from .models import Announcement, AnnouncementAudience, AnnouncementStatus

User = get_user_model()


class AdminAnnouncementTests(APITestCase):
    """Superadmins broadcast to any audience directly. Support staff can only propose
    client-facing announcements, which stay invisible until a superadmin approves them -
    see AnnouncementApprovalTests for that workflow."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super-announce@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff-announce@example.com', password='pass12345!', is_staff=True)

    def test_superadmin_can_create_an_announcement(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/announcements/', {
            'title': 'Scheduled maintenance', 'body': 'The app will be down briefly tonight.',
            'audience': 'clients',
        })
        self.assertEqual(response.status_code, 201)
        announcement = Announcement.objects.get()
        self.assertEqual(announcement.created_by_id, self.superadmin.id)

    def test_superadmin_can_send_a_staff_announcement_and_staff_sees_it(self):
        """The exact end-to-end flow: superadmin posts a 'staff' announcement through the real
        admin endpoint, then a separate staff account fetches their own announcements and
        actually sees it (not just that the two halves work in isolation)."""
        self.client.force_authenticate(user=self.superadmin)
        create_response = self.client.post('/api/admin/announcements/', {
            'title': 'Staff meeting Friday', 'body': 'All hands at 3pm.', 'audience': 'staff',
        })
        self.assertEqual(create_response.status_code, 201)

        self.client.force_authenticate(user=self.staff)
        mine_response = self.client.get('/api/announcements/mine/')
        self.assertEqual(mine_response.status_code, 200)
        titles = [a['title'] for a in mine_response.json()]
        self.assertIn('Staff meeting Friday', titles)

    def test_support_staff_cannot_update_or_delete_an_announcement(self):
        announcement = Announcement.objects.create(title='X', body='Y', audience=AnnouncementAudience.CLIENTS)
        self.client.force_authenticate(user=self.staff)
        patch_response = self.client.patch(f'/api/admin/announcements/{announcement.id}/', {'is_active': False}, format='json')
        self.assertEqual(patch_response.status_code, 403)
        delete_response = self.client.delete(f'/api/admin/announcements/{announcement.id}/')
        self.assertEqual(delete_response.status_code, 403)

    def test_superadmin_can_deactivate_an_announcement(self):
        announcement = Announcement.objects.create(title='X', body='Y', audience=AnnouncementAudience.CLIENTS)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/announcements/{announcement.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        announcement.refresh_from_db()
        self.assertFalse(announcement.is_active)

    def test_superadmin_can_delete_an_announcement(self):
        announcement = Announcement.objects.create(title='X', body='Y', audience=AnnouncementAudience.CLIENTS)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/announcements/{announcement.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Announcement.objects.exists())


class AnnouncementApprovalTests(APITestCase):
    """Support staff can propose a client-facing announcement, but it's pending and invisible
    to clients until a superadmin approves it - staff can talk to customers without being able
    to broadcast unreviewed messages to everyone at once."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super-approve@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff-approve@example.com', password='pass12345!', is_staff=True)
        self.other_staff = User.objects.create_user(username='other-staff@example.com', password='pass12345!', is_staff=True)
        self.client_user = User.objects.create_user(username='plain-approve@example.com', password='pass12345!')

    def test_staff_proposal_is_forced_to_clients_audience_and_pending_status(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post('/api/admin/announcements/', {
            'title': 'Weekend discount', 'body': '10% off this weekend.', 'audience': 'staff',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        announcement = Announcement.objects.get()
        self.assertEqual(announcement.audience, AnnouncementAudience.CLIENTS)
        self.assertEqual(announcement.status, AnnouncementStatus.PENDING)
        self.assertFalse(announcement.is_active)
        self.assertEqual(announcement.created_by_id, self.staff.id)

    def test_pending_proposal_is_not_visible_to_clients(self):
        self.client.force_authenticate(user=self.staff)
        self.client.post('/api/admin/announcements/', {
            'title': 'Weekend discount', 'body': '10% off.', 'audience': 'clients',
        }, format='json')

        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertNotIn('Weekend discount', [a['title'] for a in response.json()])

    def test_staff_only_sees_their_own_proposals_in_the_admin_list(self):
        Announcement.objects.create(
            title='Mine', body='...', audience=AnnouncementAudience.CLIENTS,
            status=AnnouncementStatus.PENDING, is_active=False, created_by=self.staff,
        )
        Announcement.objects.create(
            title='Theirs', body='...', audience=AnnouncementAudience.CLIENTS,
            status=AnnouncementStatus.PENDING, is_active=False, created_by=self.other_staff,
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/announcements/')
        self.assertEqual(response.status_code, 200)
        titles = [a['title'] for a in response.json()['results']] if 'results' in response.json() else [a['title'] for a in response.json()]
        self.assertIn('Mine', titles)
        self.assertNotIn('Theirs', titles)

    def test_staff_cannot_approve_or_reject(self):
        announcement = Announcement.objects.create(
            title='X', body='Y', audience=AnnouncementAudience.CLIENTS,
            status=AnnouncementStatus.PENDING, is_active=False, created_by=self.staff,
        )
        self.client.force_authenticate(user=self.staff)
        approve_response = self.client.post(f'/api/admin/announcements/{announcement.id}/approve/')
        self.assertEqual(approve_response.status_code, 403)
        reject_response = self.client.post(f'/api/admin/announcements/{announcement.id}/reject/')
        self.assertEqual(reject_response.status_code, 403)

    def test_superadmin_approval_makes_it_visible_to_clients(self):
        announcement = Announcement.objects.create(
            title='Weekend discount', body='10% off.', audience=AnnouncementAudience.CLIENTS,
            status=AnnouncementStatus.PENDING, is_active=False, created_by=self.staff,
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/announcements/{announcement.id}/approve/')
        self.assertEqual(response.status_code, 200)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, AnnouncementStatus.APPROVED)
        self.assertTrue(announcement.is_active)
        self.assertEqual(announcement.reviewed_by_id, self.superadmin.id)

        self.client.force_authenticate(user=self.client_user)
        mine_response = self.client.get('/api/announcements/mine/')
        self.assertIn('Weekend discount', [a['title'] for a in mine_response.json()])

    def test_superadmin_rejection_keeps_it_hidden_and_records_a_note(self):
        announcement = Announcement.objects.create(
            title='Weekend discount', body='10% off.', audience=AnnouncementAudience.CLIENTS,
            status=AnnouncementStatus.PENDING, is_active=False, created_by=self.staff,
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/announcements/{announcement.id}/reject/',
            {'review_note': 'Discount not approved by finance.'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, AnnouncementStatus.REJECTED)
        self.assertFalse(announcement.is_active)
        self.assertEqual(announcement.review_note, 'Discount not approved by finance.')

        self.client.force_authenticate(user=self.client_user)
        mine_response = self.client.get('/api/announcements/mine/')
        self.assertNotIn('Weekend discount', [a['title'] for a in mine_response.json()])

        self.client.force_authenticate(user=self.staff)
        own_response = self.client.get(f'/api/admin/announcements/{announcement.id}/')
        self.assertEqual(own_response.json()['status'], 'rejected')
        self.assertEqual(own_response.json()['review_note'], 'Discount not approved by finance.')


class MyAnnouncementsTests(APITestCase):
    """Each user only sees active announcements aimed at an audience they actually belong to -
    a plain customer always matches 'clients'; staff/drivers can match more than one."""

    def setUp(self):
        self.client_user = User.objects.create_user(username='plain-client@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff-view@example.com', password='pass12345!', is_staff=True)
        driver_user = User.objects.create_user(username='driver-view@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Announce Driver', is_active=True)
        self.driver_user = driver_user

        self.for_clients = Announcement.objects.create(title='For clients', body='...', audience=AnnouncementAudience.CLIENTS)
        self.for_staff = Announcement.objects.create(title='For staff', body='...', audience=AnnouncementAudience.STAFF)
        self.for_drivers = Announcement.objects.create(title='For drivers', body='...', audience=AnnouncementAudience.DRIVERS)
        self.inactive = Announcement.objects.create(
            title='Inactive', body='...', audience=AnnouncementAudience.CLIENTS, is_active=False,
        )

    def _titles(self, response):
        return {a['title'] for a in response.json()}

    def test_plain_client_sees_only_client_announcements(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._titles(response), {'For clients'})

    def test_staff_sees_staff_and_client_announcements(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/announcements/mine/')
        self.assertEqual(self._titles(response), {'For clients', 'For staff'})

    def test_driver_sees_driver_and_client_announcements(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertEqual(self._titles(response), {'For clients', 'For drivers'})

    def test_inactive_announcements_never_appear(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertNotIn('Inactive', self._titles(response))

    def test_suspended_driver_no_longer_sees_driver_announcements(self):
        self.driver.is_active = False
        self.driver.save(update_fields=['is_active'])
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertEqual(self._titles(response), {'For clients'})

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/announcements/mine/')
        self.assertEqual(response.status_code, 401)

    def test_marking_an_announcement_read_reflects_in_is_read(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertFalse(next(a for a in response.json() if a['title'] == 'For clients')['is_read'])

        mark_response = self.client.post(f'/api/announcements/{self.for_clients.id}/mark-read/')
        self.assertEqual(mark_response.status_code, 204)

        response = self.client.get('/api/announcements/mine/')
        self.assertTrue(next(a for a in response.json() if a['title'] == 'For clients')['is_read'])

    def test_cannot_mark_read_an_announcement_not_meant_for_you(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(f'/api/announcements/{self.for_staff.id}/mark-read/')
        self.assertEqual(response.status_code, 404)


class AnnouncementExpiryTests(APITestCase):
    """expires_at is optional - null means it never expires on its own. Past expires_at should
    stop an otherwise-active, approved announcement from showing up at all."""

    def setUp(self):
        self.client_user = User.objects.create_user(username='expiry-client@example.com', password='pass12345!')
        self.superadmin = User.objects.create_superuser(username='expiry-super@example.com', password='pass12345!')

    def test_expired_announcement_is_not_visible(self):
        Announcement.objects.create(
            title='Expired', body='...', audience=AnnouncementAudience.CLIENTS,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertNotIn('Expired', [a['title'] for a in response.json()])

    def test_future_expiry_still_visible(self):
        Announcement.objects.create(
            title='Not yet expired', body='...', audience=AnnouncementAudience.CLIENTS,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertIn('Not yet expired', [a['title'] for a in response.json()])

    def test_no_expiry_set_is_always_visible(self):
        Announcement.objects.create(title='No expiry', body='...', audience=AnnouncementAudience.CLIENTS)
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/announcements/mine/')
        self.assertIn('No expiry', [a['title'] for a in response.json()])

    def test_cannot_mark_read_an_expired_announcement(self):
        expired = Announcement.objects.create(
            title='Expired', body='...', audience=AnnouncementAudience.CLIENTS,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post(f'/api/announcements/{expired.id}/mark-read/')
        self.assertEqual(response.status_code, 404)

    def test_superadmin_can_set_expires_at_on_create(self):
        self.client.force_authenticate(user=self.superadmin)
        expiry = (timezone.now() + timedelta(days=7)).isoformat()
        response = self.client.post('/api/admin/announcements/', {
            'title': 'Sale ends soon', 'body': '...', 'audience': 'clients', 'expires_at': expiry,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        announcement = Announcement.objects.get()
        self.assertIsNotNone(announcement.expires_at)
