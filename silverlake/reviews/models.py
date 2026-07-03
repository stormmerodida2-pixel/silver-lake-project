from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


class Review(models.Model):
    customer_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    is_approved = models.BooleanField(default=False, help_text='Only approved reviews show on the public site')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer_name} ({self.rating}/5)'
