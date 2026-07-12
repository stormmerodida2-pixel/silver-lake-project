from rest_framework import permissions, viewsets

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ReadOnlyModelViewSet):
    """Public, read-only, approved reviews only. Reviews are never created here directly -
    the only legitimate way to leave one is BookingViewSet.review, which requires being
    logged in and reviewing your own completed trip. Admin moderation (approve/reject/delete)
    lives separately on AdminReviewViewSet."""

    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Review.objects.filter(is_approved=True)
