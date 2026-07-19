from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import StaffOrganization
from fleet.models import FleetPartner

from .models import DiscountCode, DiscountType
from .services import DiscountCodeError, find_active_code, reserve_code

User = get_user_model()


class DiscountCodeModelTests(APITestCase):
    def test_code_is_uppercased_and_stripped_on_save(self):
        code = DiscountCode.objects.create(code='  save1000  ', value=Decimal('500'))
        self.assertEqual(code.code, 'SAVE1000')

    def test_blank_code_is_auto_generated(self):
        code = DiscountCode.objects.create(value=Decimal('500'))
        self.assertEqual(len(code.code), 8)
        self.assertTrue(code.code.isalnum())

    def test_fixed_discount_never_exceeds_the_total(self):
        code = DiscountCode.objects.create(code='BIG', discount_type=DiscountType.FIXED, value=Decimal('5000'))
        self.assertEqual(code.compute_discount(Decimal('3000')), Decimal('3000'))

    def test_percent_discount_is_computed_off_the_total(self):
        code = DiscountCode.objects.create(code='TENOFF', discount_type=DiscountType.PERCENT, value=Decimal('10'))
        self.assertEqual(code.compute_discount(Decimal('2000')), Decimal('200.00'))


class ReserveCodeTests(APITestCase):
    """discounts.services.reserve_code is the atomic single-use guarantee - see its own
    docstring for why a plain read-then-check isn't enough."""

    def test_reserve_code_marks_it_redeemed(self):
        DiscountCode.objects.create(code='ONEUSE', value=Decimal('100'))
        reserved = reserve_code('oneuse')
        self.assertTrue(reserved.is_redeemed)
        self.assertTrue(DiscountCode.objects.get(code='ONEUSE').is_redeemed)

    def test_reserve_code_rejects_an_already_redeemed_code(self):
        DiscountCode.objects.create(code='USED', value=Decimal('100'), is_redeemed=True)
        with self.assertRaises(DiscountCodeError):
            reserve_code('USED')

    def test_reserve_code_rejects_an_inactive_code(self):
        DiscountCode.objects.create(code='OFF', value=Decimal('100'), is_active=False)
        with self.assertRaises(DiscountCodeError):
            reserve_code('OFF')

    def test_reserve_code_rejects_an_unknown_code(self):
        with self.assertRaises(DiscountCodeError):
            reserve_code('NOSUCHCODE')

    def test_find_active_code_does_not_itself_reserve_it(self):
        DiscountCode.objects.create(code='PREVIEW', value=Decimal('100'))
        find_active_code('preview')
        self.assertFalse(DiscountCode.objects.get(code='PREVIEW').is_redeemed)


class AdminDiscountCodeViewSetTests(APITestCase):
    """Only a genuine SilverLake platform superadmin manages discount codes - see
    IsPlatformSuperAdmin - not a FleetPartner's own org-admin (also is_superuser=True, but
    scoped) and not day-to-day support staff."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super-disc@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff-disc@example.com', password='pass12345!', is_staff=True)
        org = FleetPartner.objects.create(name='Discount Org', platform_fee_percent=Decimal('10'))
        self.org_admin = User.objects.create_user(
            username='org-admin-disc@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_admin, organization=org)

    def test_platform_superadmin_can_create_a_discount_code(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/discounts/', {
            'code': 'WELCOME500', 'discount_type': 'fixed', 'value': '500',
        })
        self.assertEqual(response.status_code, 201)
        code = DiscountCode.objects.get()
        self.assertEqual(code.code, 'WELCOME500')
        self.assertEqual(code.created_by_id, self.superadmin.id)

    def test_code_is_optional_and_auto_generated_via_the_api(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/discounts/', {'discount_type': 'percent', 'value': '10'})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['code'])

    def test_support_staff_cannot_manage_discount_codes(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post('/api/admin/discounts/', {'value': '500'})
        self.assertEqual(response.status_code, 403)

    def test_org_admin_cannot_manage_discount_codes(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post('/api/admin/discounts/', {'value': '500'})
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_manage_discount_codes(self):
        response = self.client.get('/api/admin/discounts/')
        self.assertIn(response.status_code, (401, 403))

    def test_percentage_over_100_is_rejected(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/discounts/', {'discount_type': 'percent', 'value': '150'})
        self.assertEqual(response.status_code, 400)

    def test_zero_value_is_rejected(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/discounts/', {'value': '0'})
        self.assertEqual(response.status_code, 400)

    def test_duplicate_code_is_rejected_case_insensitively(self):
        DiscountCode.objects.create(code='DUP', value=Decimal('100'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/discounts/', {'code': 'dup', 'value': '50'})
        self.assertEqual(response.status_code, 400)

    def test_superadmin_can_deactivate_a_code(self):
        code = DiscountCode.objects.create(code='OFFME', value=Decimal('100'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/discounts/{code.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        code.refresh_from_db()
        self.assertFalse(code.is_active)

    def test_superadmin_can_delete_a_code(self):
        code = DiscountCode.objects.create(code='DELME', value=Decimal('100'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/discounts/{code.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DiscountCode.objects.filter(pk=code.id).exists())
