from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from drivers.models import Driver

from .models import Review

User = get_user_model()


class DriverRatingRecalculationTests(APITestCase):
    """Driver.rating defaults to 5.0 and otherwise never changes on its own - it has to be
    recomputed from approved reviews whenever moderation changes what's approved."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super6@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Rated Driver', is_active=True)
        self.client.force_authenticate(user=self.superadmin)

    def test_approving_a_review_updates_the_drivers_rating(self):
        review = Review.objects.create(
            driver=self.driver, customer_name='Jane', rating=3, comment='Fine.', is_approved=False,
        )
        self.assertEqual(self.driver.rating, Decimal('5.00'))

        response = self.client.post(f'/api/admin/reviews/{review.id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, Decimal('3.00'))

    def test_rating_is_the_average_of_all_approved_reviews(self):
        Review.objects.create(driver=self.driver, customer_name='A', rating=5, comment='Great', is_approved=True)
        review = Review.objects.create(driver=self.driver, customer_name='B', rating=3, comment='OK', is_approved=False)

        self.client.post(f'/api/admin/reviews/{review.id}/approve/')
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, Decimal('4.00'))

    def test_rejecting_a_previously_approved_review_recalculates(self):
        review = Review.objects.create(driver=self.driver, customer_name='A', rating=1, comment='Bad', is_approved=True)
        self.driver.recalculate_rating()
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, Decimal('1.00'))

        response = self.client.post(f'/api/admin/reviews/{review.id}/reject/')
        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, Decimal('5.00'))

    def test_deleting_an_approved_review_recalculates(self):
        review = Review.objects.create(driver=self.driver, customer_name='A', rating=2, comment='Meh', is_approved=True)
        self.driver.recalculate_rating()

        response = self.client.delete(f'/api/admin/reviews/{review.id}/')
        self.assertEqual(response.status_code, 204)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, Decimal('5.00'))

    def test_unapproved_reviews_dont_count_towards_the_rating(self):
        Review.objects.create(driver=self.driver, customer_name='A', rating=1, comment='Unapproved', is_approved=False)
        self.driver.recalculate_rating()
        self.assertEqual(self.driver.rating, Decimal('5.00'))


class PublicReviewApiTests(APITestCase):
    """The public /api/reviews/ endpoint is read-only - the only legitimate way to leave a
    review is reviewing your own completed booking (see bookings.tests.BookingReviewActionTests),
    never a free-form submission with no booking behind it. Driver identity is also never
    exposed on this public surface, even though admins need to see it to moderate."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Hidden Driver', is_active=True)
        self.review = Review.objects.create(
            driver=self.driver, customer_name='Jane', rating=5, comment='Great trip!', is_approved=True,
        )

    def test_approved_reviews_are_publicly_listed_without_driver_details(self):
        response = self.client.get('/api/reviews/')
        self.assertEqual(response.status_code, 200)
        results = response.json().get('results', response.json())
        self.assertEqual(len(results), 1)
        self.assertNotIn('driver_name', results[0])
        self.assertNotIn('driver', results[0])

    def test_unapproved_reviews_are_not_publicly_listed(self):
        Review.objects.create(customer_name='Bob', rating=2, comment='Meh', is_approved=False)
        response = self.client.get('/api/reviews/')
        results = response.json().get('results', response.json())
        self.assertEqual(len(results), 1)

    def test_anonymous_users_cannot_submit_a_free_form_review(self):
        response = self.client.post('/api/reviews/', {
            'customer_name': 'Anyone', 'rating': 5, 'comment': 'Never actually booked anything',
        })
        self.assertIn(response.status_code, (403, 405))
        self.assertEqual(Review.objects.count(), 1)  # still just the one from setUp

    def test_logged_in_users_also_cannot_submit_via_the_public_endpoint(self):
        user = User.objects.create_user(username='reviewer@example.com', password='pass12345!')
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/reviews/', {
            'customer_name': 'Anyone', 'rating': 5, 'comment': 'Still no booking behind this',
        })
        self.assertIn(response.status_code, (403, 405))
        self.assertEqual(Review.objects.count(), 1)


class DjangoAdminReviewActionTests(APITestCase):
    """The Django admin's bulk approve action used to call queryset.update(), which bypasses
    save() entirely - a driver's rating would silently go stale for anything approved this way
    instead of through the real admin dashboard. Tests the ModelAdmin action directly (rather
    than via the /admin/ URL) since that URL is only registered when DEBUG is on, and Django's
    test runner always forces DEBUG off."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from .admin import ReviewAdmin

        self.superadmin = User.objects.create_superuser(username='django-admin-super2@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Django Review Driver', is_active=True)
        self.review = Review.objects.create(
            driver=self.driver, customer_name='Jane', rating=2, comment='Fine', is_approved=False,
        )

        self.admin = ReviewAdmin(Review, AdminSite())
        request = RequestFactory().post('/admin/reviews/review/')
        request.user = self.superadmin
        request.session = {}
        request._messages = FallbackStorage(request)
        self.request = request

    def test_bulk_approve_recalculates_the_drivers_rating(self):
        self.assertEqual(self.driver.rating, Decimal('5.00'))
        self.admin.approve_reviews(self.request, Review.objects.filter(pk=self.review.pk))
        self.review.refresh_from_db()
        self.driver.refresh_from_db()
        self.assertTrue(self.review.is_approved)
        self.assertEqual(self.driver.rating, Decimal('2.00'))
