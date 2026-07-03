from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    """Optional profile for a registered customer account, linked to Django's built-in User."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='customer_profile')
    phone_number = models.CharField(max_length=20, blank=True)
    id_number = models.CharField(max_length=30, blank=True, help_text='National ID or passport number')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username
