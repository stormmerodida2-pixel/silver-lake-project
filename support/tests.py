from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from bookings.tests import make_booking, make_vehicle
from core.models import StaffOrganization
from fleet.models import FleetPartner

from .models import SupportTicket, TicketStatus

User = get_user_model()


class MySupportTicketTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username='support-client@example.com', password='pass12345!', email='support-client@example.com')
        self.other_customer = User.objects.create_user(username='support-other@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle)
        self.client.force_authenticate(user=self.customer)

    def test_customer_can_file_a_ticket(self):
        User.objects.create_user(
            username='support-staff-recipient@example.com', password='pass12345!',
            email='support-staff-recipient@example.com', is_staff=True,
        )
        mail.outbox = []
        response = self.client.post('/api/support/tickets/', {
            'category': 'billing', 'subject': 'Overcharged', 'description': 'I was charged twice.',
        })
        self.assertEqual(response.status_code, 201)
        ticket = SupportTicket.objects.get()
        self.assertEqual(ticket.user, self.customer)
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertTrue(any('New support ticket' in m.subject for m in mail.outbox))

    def test_customer_can_attach_their_own_booking(self):
        response = self.client.post('/api/support/tickets/', {
            'category': 'damage_dispute', 'subject': 'Disputed charge', 'description': 'Not my fault.',
            'booking': self.booking.id,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SupportTicket.objects.get().booking_id, self.booking.id)

    def test_customer_cannot_attach_someone_elses_booking(self):
        other_booking = make_booking(self.other_customer, self.vehicle, start_date=self.booking.end_date, end_date=self.booking.end_date)
        response = self.client.post('/api/support/tickets/', {
            'category': 'damage_dispute', 'subject': 'X', 'description': 'Y', 'booking': other_booking.id,
        })
        self.assertEqual(response.status_code, 400)

    def test_photos_are_attached_to_the_ticket(self):
        photo = SimpleUploadedFile('evidence.jpg', b'x', content_type='image/jpeg')
        response = self.client.post(
            '/api/support/tickets/',
            {'category': 'other', 'subject': 'X', 'description': 'Y', 'photos': [photo]},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()['photos']), 1)

    def test_customer_only_sees_their_own_tickets(self):
        SupportTicket.objects.create(user=self.other_customer, subject='Not mine', description='...')
        SupportTicket.objects.create(user=self.customer, subject='Mine', description='...')
        response = self.client.get('/api/support/tickets/')
        subjects = [t['subject'] for t in response.json()['results']] if 'results' in response.json() else [t['subject'] for t in response.json()]
        self.assertEqual(subjects, ['Mine'])

    def test_customer_can_reopen_a_resolved_ticket(self):
        ticket = SupportTicket.objects.create(
            user=self.customer, subject='X', description='Y', status=TicketStatus.RESOLVED, resolution_note='Fixed it.',
        )
        response = self.client.post(f'/api/support/tickets/{ticket.id}/reopen/')
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.resolution_note, 'Fixed it.')  # left in place, not cleared

    def test_customer_cannot_reopen_an_open_ticket(self):
        ticket = SupportTicket.objects.create(user=self.customer, subject='X', description='Y')
        response = self.client.post(f'/api/support/tickets/{ticket.id}/reopen/')
        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_reopen_someone_elses_ticket(self):
        ticket = SupportTicket.objects.create(
            user=self.other_customer, subject='X', description='Y', status=TicketStatus.RESOLVED,
        )
        response = self.client.post(f'/api/support/tickets/{ticket.id}/reopen/')
        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_file_a_ticket(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/support/tickets/', {'category': 'other', 'subject': 'X', 'description': 'Y'})
        self.assertIn(response.status_code, (401, 403))


class AdminSupportTicketTests(APITestCase):
    def setUp(self):
        self.platform_staff = User.objects.create_user(username='support-staff@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='support-ticket-client@example.com', password='pass12345!', email='support-ticket-client@example.com')
        self.ticket = SupportTicket.objects.create(user=self.customer, subject='Billing question', description='Why was I charged KES 500?')
        self.client.force_authenticate(user=self.platform_staff)

    def test_platform_staff_can_list_tickets(self):
        response = self.client.get('/api/admin/support/')
        self.assertEqual(response.status_code, 200)

    def test_org_admin_cannot_access_support_tickets(self):
        org = FleetPartner.objects.create(name='Support Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='support-org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)
        self.client.force_authenticate(user=org_admin)
        response = self.client.get('/api/admin/support/')
        self.assertEqual(response.status_code, 403)

    def test_plain_customer_cannot_access_admin_support(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin/support/')
        self.assertEqual(response.status_code, 403)

    def test_staff_can_mark_a_ticket_in_progress_without_a_note(self):
        response = self.client.post(f'/api/admin/support/{self.ticket.id}/respond/', {'status': 'in_progress'})
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)

    def test_marking_in_progress_notifies_the_customer(self):
        mail.outbox = []
        self.client.post(f'/api/admin/support/{self.ticket.id}/respond/', {'status': 'in_progress'})

        from notifications.models import Notification, NotificationEvent

        self.assertTrue(
            Notification.objects.filter(
                event=NotificationEvent.SUPPORT_TICKET_IN_PROGRESS, user=self.customer,
            ).exists()
        )
        self.assertTrue(any('looking into' in m.subject for m in mail.outbox))
        self.assertIn('support-ticket-client@example.com', mail.outbox[-1].to)

    def test_resolving_a_ticket_requires_a_resolution_note(self):
        response = self.client.post(f'/api/admin/support/{self.ticket.id}/respond/', {'status': 'resolved'})
        self.assertEqual(response.status_code, 400)

    def test_staff_can_resolve_a_ticket_with_a_note(self):
        mail.outbox = []
        response = self.client.post(
            f'/api/admin/support/{self.ticket.id}/respond/',
            {'status': 'resolved', 'resolution_note': 'Refunded the duplicate charge.'},
        )
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.RESOLVED)
        self.assertEqual(self.ticket.resolution_note, 'Refunded the duplicate charge.')
        self.assertEqual(self.ticket.resolved_by, self.platform_staff)
        self.assertIsNotNone(self.ticket.resolved_at)
        self.assertTrue(any('resolved' in m.subject for m in mail.outbox))
        self.assertIn('support-ticket-client@example.com', mail.outbox[-1].to)

    def test_invalid_status_is_rejected(self):
        response = self.client.post(f'/api/admin/support/{self.ticket.id}/respond/', {'status': 'bogus'})
        self.assertEqual(response.status_code, 400)
