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
