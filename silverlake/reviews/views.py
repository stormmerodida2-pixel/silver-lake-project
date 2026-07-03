from rest_framework import permissions, viewsets

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """Public can read approved reviews and submit new ones; new submissions await admin approval."""

    serializer_class = ReviewSerializer

    def get_queryset(self):
        if self.action in ('list', 'retrieve'):
            return Review.objects.filter(is_approved=True)
        return Review.objects.all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'create'):
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
