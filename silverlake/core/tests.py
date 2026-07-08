from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver, DriverApplication
from fleet.models import VehicleCategory, VehicleImage, VehicleSubmission
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus, Refund

from .models import AuditLog

User = get_user_model()


class AdminPayoutVerificationTests(APITestCase):
    """A payout confirmed via self-reported cash must be explicitly verified by a superadmin
    before it can be marked paid - closes the gap where a fabricated cash claim would otherwise
    sail straight through to a real payout."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff@example.com', password='pass12345!', is_staff=True)

        self.driver = Driver.objects.create(full_name='Payout Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)

        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)
        assert self.payout.needs_verification and not self.payout.is_verified

    def test_cannot_mark_paid_before_verifying(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 400)
        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_paid)

    def test_support_staff_cannot_verify_a_payout(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/')
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_verify_then_mark_paid(self):
        self.client.force_authenticate(user=self.superadmin)

        verify_response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/')
        self.assertEqual(verify_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_verified)
        self.assertIsNotNone(self.payout.verified_at)

        pay_response = self.client.post(
            f'/api/admin/payouts/{self.payout.id}/mark-paid/', {'payout_reference': 'MPESA123'},
        )
        self.assertEqual(pay_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_paid)

    def test_mpesa_sourced_payout_can_be_marked_paid_without_verification(self):
        other_customer = User.objects.create_user(username='other-client@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='Other Car', driver=self.driver, price_per_day=Decimal('1000'))
        other_booking = make_booking(other_customer, other_vehicle, driver=self.driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=other_booking, method=PaymentMethod.MPESA,
            amount=other_booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        other_booking.confirm_if_deposit_met()
        other_payout = DriverPayout.objects.get(booking=other_booking)
        self.assertFalse(other_payout.needs_verification)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{other_payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 200)

    def test_cannot_mark_paid_a_voided_payout(self):
        self.payout.is_verified = True
        self.payout.void()
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 400)


class AdminRefundActionTests(APITestCase):
    """A refund gets auto-created when a paid booking is cancelled (see bookings.tests); this
    covers admin's ability to see and act on it."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super2@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff2@example.com', password='pass12345!', is_staff=True)
        vehicle = make_vehicle(name='Refund Car', price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='refund-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.mark_cancelled()
        self.refund = Refund.objects.get(booking=booking)

    def test_support_staff_can_list_refunds(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/refunds/')
        self.assertEqual(response.status_code, 200)

    def test_support_staff_cannot_mark_a_refund_issued(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/')
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_mark_a_refund_issued(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/', {'reference': 'MPESA-REFUND-1'})
        self.assertEqual(response.status_code, 200)
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.status, 'issued')
        self.assertEqual(self.refund.reference, 'MPESA-REFUND-1')
        self.assertIsNotNone(self.refund.issued_at)


class AdminAuditLogTests(APITestCase):
    """Sensitive admin actions (role changes, suspensions, payouts, refunds) must leave a
    record of who did them - otherwise a two-tier permission system can't answer 'who did this'."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super3@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff3@example.com', password='pass12345!', is_staff=True)

    def test_suspending_a_driver_is_logged(self):
        driver = Driver.objects.create(full_name='Logged Driver', is_active=True)
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/drivers/{driver.id}/suspend/', {'reason': 'Complaint received'})

        entry = AuditLog.objects.get(action='driver.suspend')
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.target_repr, driver.full_name)
        self.assertEqual(entry.detail, 'Complaint received')

    def test_promoting_a_user_to_staff_is_logged(self):
        target = User.objects.create_user(username='promote-me@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/users/{target.id}/', {'is_staff': True}, format='json')

        entry = AuditLog.objects.get(action='user.update_roles')
        self.assertEqual(entry.actor, self.superadmin)
        self.assertIn('is_staff=True', entry.detail)

    def test_editing_a_user_without_changing_roles_is_not_logged(self):
        target = User.objects.create_user(username='no-role-change@example.com', password='pass12345!', first_name='Old')
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/users/{target.id}/', {'first_name': 'New'}, format='json')

        self.assertFalse(AuditLog.objects.filter(action='user.update_roles').exists())

    def test_unauthenticated_user_cannot_view_the_audit_log(self):
        response = self.client.get('/api/admin/audit-log/')
        self.assertEqual(response.status_code, 401)

    def test_reassigning_a_bookings_driver_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='audit-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, status=BookingStatus.PENDING)
        driver = Driver.objects.create(full_name='Audit Driver', is_active=True)

        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/bookings/{booking.id}/', {'driver': driver.id}, format='json')

        entry = AuditLog.objects.get(action='booking.update')
        self.assertEqual(entry.actor, self.superadmin)
        self.assertIn(str(driver.id), entry.detail)

    def test_creating_a_vehicle_is_logged(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            '/api/admin/fleet/',
            {'name': 'Audited Car', 'category': 'compact_sedan', 'passenger_capacity': 4, 'price_per_day': '1000'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action='vehicle.create').exists())

    def test_updating_a_vehicle_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'price_per_day': '1200'}, format='json')
        self.assertTrue(AuditLog.objects.filter(action='vehicle.update').exists())

    def test_adding_a_gallery_image_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        self.client.post(
            f'/api/admin/fleet/{vehicle.id}/gallery/',
            {'images': [SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg')]}, format='multipart',
        )
        self.assertTrue(AuditLog.objects.filter(action='vehicle.add_gallery_images').exists())

    def test_removing_a_gallery_image_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        image = VehicleImage.objects.create(
            vehicle=vehicle, image=SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'),
        )
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/fleet/{vehicle.id}/gallery/{image.id}/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle.remove_gallery_image').exists())

    def test_approving_a_review_is_logged(self):
        from reviews.models import Review

        review = Review.objects.create(customer_name='Jane', rating=5, comment='Great!', is_approved=False)
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/reviews/{review.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='review.approve').exists())

    def test_deleting_a_review_is_logged(self):
        from reviews.models import Review

        review = Review.objects.create(customer_name='Jane', rating=5, comment='Great!', is_approved=True)
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/reviews/{review.id}/')
        self.assertTrue(AuditLog.objects.filter(action='review.delete').exists())

    def test_approving_a_driver_application_is_logged(self):
        from drivers.models import DriverApplication

        category, _ = VehicleCategory.objects.get_or_create(
            slug='premium_mpv', defaults={'name': 'Premium MPV'},
        )
        application = DriverApplication.objects.create(
            full_name='Applicant', email='applicant@example.com', phone_number='254700000000',
            license_number='DL1', license_document=SimpleUploadedFile('l.jpg', b'x', content_type='image/jpeg'),
            vehicle_name='Toyota Noah', vehicle_category=category,
            passenger_capacity=7, price_per_day=5000,
        )
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/driver-applications/{application.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='driver_application.approve').exists())

    def test_approving_a_vehicle_submission_is_logged(self):
        from fleet.models import VehicleSubmission

        driver = Driver.objects.create(full_name='Submitting Driver', is_active=True)
        category, _ = VehicleCategory.objects.get_or_create(
            slug='premium_mpv', defaults={'name': 'Premium MPV'},
        )
        submission = VehicleSubmission.objects.create(
            driver=driver, name='Submitted Car', category=category,
            passenger_capacity=7, price_per_day=5000,
            logbook_document=SimpleUploadedFile('logbook.pdf', b'x', content_type='application/pdf'),
        )
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/vehicle-submissions/{submission.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle_submission.approve').exists())


class CascadeDeleteProtectionTests(APITestCase):
    """Deleting a user/driver/vehicle must never silently take their bookings/payouts with
    them - that's exactly the financial trail the rest of this app is built to preserve."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super4@example.com', password='pass12345!')

    def test_deleting_a_user_with_bookings_is_blocked(self):
        customer = User.objects.create_user(username='has-bookings@example.com', password='pass12345!')
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        make_booking(customer, vehicle, status=BookingStatus.PENDING)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/users/{customer.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(id=customer.id).exists())

    def test_deleting_a_user_with_no_bookings_still_works(self):
        customer = User.objects.create_user(username='no-bookings@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/users/{customer.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=customer.id).exists())

    def test_deleting_a_driver_with_payouts_is_blocked(self):
        driver = Driver.objects.create(full_name='Payout History Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='payout-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()
        self.assertTrue(DriverPayout.objects.filter(driver=driver).exists())

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/drivers/{driver.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Driver.objects.filter(id=driver.id).exists())
        self.assertTrue(DriverPayout.objects.filter(driver=driver).exists())

    def test_deleting_a_driver_with_no_payouts_still_works(self):
        driver = Driver.objects.create(full_name='Clean Driver', is_active=True)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/drivers/{driver.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Driver.objects.filter(id=driver.id).exists())

    def test_deleting_a_vehicle_with_bookings_is_blocked(self):
        customer = User.objects.create_user(username='vehicle-client@example.com', password='pass12345!')
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        make_booking(customer, vehicle, status=BookingStatus.PENDING)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{vehicle.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('bookings on file', response.json()['detail'])


class AdminVehicleDriverAssignmentTests(APITestCase):
    """Admin needs to be able to say who drives a company-owned vehicle - otherwise a
    with-driver booking on it never has a driver to notify, pay out, or complete the trip."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super5@example.com', password='pass12345!')

    def test_superadmin_can_assign_a_driver_to_a_vehicle(self):
        driver = Driver.objects.create(full_name='Company Driver', is_active=True)
        vehicle = make_vehicle(price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': driver.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['driver'], driver.id)
        self.assertEqual(response.json()['driver_name'], driver.full_name)

        vehicle.refresh_from_db()
        self.assertEqual(vehicle.driver_id, driver.id)

    def test_a_vehicle_with_no_driver_reports_a_null_driver_name(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(f'/api/admin/fleet/{vehicle.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['driver'])
        self.assertIsNone(response.json()['driver_name'])

    def test_cannot_assign_a_suspended_driver(self):
        suspended_driver = Driver.objects.create(full_name='Suspended Driver', is_active=False)
        vehicle = make_vehicle(price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': suspended_driver.id}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_driver_can_be_cleared_back_to_none(self):
        driver = Driver.objects.create(full_name='Removable Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': ''}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.driver_id)


class AdminBookingEditTests(APITestCase):
    """Admin needs a way to fix a booking assigned to the wrong driver (e.g. one created before
    its vehicle had a driver set) - a status change alone can't do that."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super7@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff7@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='edit-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)

    def test_superadmin_can_reassign_the_driver(self):
        driver = Driver.objects.create(full_name='Reassigned Driver', is_active=True)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/bookings/{self.booking.id}/', {'driver': driver.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.driver_id, driver.id)

    def test_support_staff_cannot_edit_a_booking(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(f'/api/admin/bookings/{self.booking.id}/', {'notes': 'Changed'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_support_staff_can_still_change_status(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'confirmed'})
        self.assertEqual(response.status_code, 200)


class AdminVehicleGalleryTests(APITestCase):
    """A company-created vehicle previously had no way to get more than its single cover photo -
    only a driver's own submission required (and got) a real photo gallery."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super8@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff8@example.com', password='pass12345!', is_staff=True)
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))

    def _image(self, name='photo.jpg'):
        return SimpleUploadedFile(name, b'fake-image-bytes', content_type='image/jpeg')

    def test_superadmin_can_add_gallery_images(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/gallery/',
            {'images': [self._image('a.jpg'), self._image('b.jpg')]}, format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(VehicleImage.objects.filter(vehicle=self.vehicle).count(), 2)

    def test_support_staff_cannot_add_gallery_images(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/gallery/', {'images': [self._image()]}, format='multipart',
        )
        self.assertEqual(response.status_code, 403)

    def test_adding_with_no_images_is_rejected(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/fleet/{self.vehicle.id}/gallery/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_superadmin_can_remove_a_gallery_image(self):
        image = VehicleImage.objects.create(vehicle=self.vehicle, image=self._image())
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{self.vehicle.id}/gallery/{image.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(VehicleImage.objects.filter(id=image.id).exists())

    def test_cannot_remove_a_gallery_image_belonging_to_another_vehicle(self):
        other_vehicle = make_vehicle(name='Other Car', price_per_day=Decimal('1000'))
        image = VehicleImage.objects.create(vehicle=other_vehicle, image=self._image())
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{self.vehicle.id}/gallery/{image.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(VehicleImage.objects.filter(id=image.id).exists())


class AdminVehicleCategoryTests(APITestCase):
    """Fleet types used to be a fixed enum in code - now a plain admin-editable list.
    Create/update/delete are superadmin-only (fleet composition tier); support staff can
    still list them to populate forms. Deleting one still referenced by a vehicle,
    submission, or driver application must be blocked, not silently orphan those records."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super9@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff9@example.com', password='pass12345!', is_staff=True)

    def test_anyone_authenticated_as_staff_can_list_categories(self):
        VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/fleet-types/')
        self.assertEqual(response.status_code, 200)
        names = [c['name'] for c in response.json().get('results', response.json())]
        self.assertIn('Luxury Convertible', names)

    def test_superadmin_can_create_a_category_with_an_auto_generated_slug(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/fleet-types/', {'name': 'Luxury Convertible', 'order': 5})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['slug'], 'luxury-convertible')
        self.assertTrue(VehicleCategory.objects.filter(slug='luxury-convertible').exists())

    def test_support_staff_cannot_create_a_category(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post('/api/admin/fleet-types/', {'name': 'Luxury Convertible'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VehicleCategory.objects.filter(name='Luxury Convertible').exists())

    def test_support_staff_cannot_delete_a_category(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_superadmin_can_delete_an_unused_category(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_vehicle_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        make_vehicle(category=category, price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_vehicle_submission_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        driver = Driver.objects.create(full_name='Submitting Driver', is_active=True)
        VehicleSubmission.objects.create(
            driver=driver, name='Submitted Car', category=category,
            passenger_capacity=4, price_per_day=5000,
            logbook_document=SimpleUploadedFile('logbook.pdf', b'x', content_type='application/pdf'),
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_driver_application_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        DriverApplication.objects.create(
            full_name='Applicant', email='applicant@example.com', phone_number='254700000000',
            license_number='DL1', license_document=SimpleUploadedFile('l.jpg', b'x', content_type='image/jpeg'),
            vehicle_name='Convertible One', vehicle_category=category,
            passenger_capacity=2, price_per_day=8000,
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_is_logged(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle_category.delete').exists())
