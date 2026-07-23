from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    # Set when the review comes from a customer reviewing their own completed trip - the
    # normal path now. Left null for the older free-form testimonials submitted with no
    # booking context, so those keep working unchanged.
    booking = models.OneToOneField(
        'bookings.Booking', null=True, blank=True, on_delete=models.SET_NULL, related_name='review',
    )
    driver = models.ForeignKey(
        'drivers.Driver', null=True, blank=True, on_delete=models.SET_NULL, related_name='reviews',
    )
    customer_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    is_approved = models.BooleanField(default=False, help_text='Only approved reviews show on the public site')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_name} ({self.rating}/5)'
