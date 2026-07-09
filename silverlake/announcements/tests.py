from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from drivers.models import Driver

from .models import Announcement, AnnouncementAudience

User = get_user_model()


class AdminAnnouncementTests(APITestCase):
    """Broadcasting to a whole audience is significant enough to be superadmin-only, not a
    day-to-day support-staff action."""

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

    def test_support_staff_cannot_create_an_announcement(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post('/api/admin/announcements/', {
            'title': 'Scheduled maintenance', 'body': 'Down tonight.', 'audience': 'clients',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Announcement.objects.exists())

    def test_support_staff_cannot_list_announcements_in_the_admin_endpoint(self):
        Announcement.objects.create(title='X', body='Y', audience=AnnouncementAudience.STAFF)
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/announcements/')
        self.assertEqual(response.status_code, 403)

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
