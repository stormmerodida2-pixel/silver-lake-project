from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminBookingViewSet,
    AdminDriverApplicationViewSet,
    AdminDriverPayoutViewSet,
    AdminDriverViewSet,
    AdminFleetViewSet,
    AdminReviewViewSet,
    AdminStatsView,
    AdminUserViewSet,
)

router = DefaultRouter()
router.register('admin/users', AdminUserViewSet, basename='admin-user')
router.register('admin/drivers', AdminDriverViewSet, basename='admin-driver')
router.register('admin/driver-applications', AdminDriverApplicationViewSet, basename='admin-driver-application')
router.register('admin/bookings', AdminBookingViewSet, basename='admin-booking')
router.register('admin/payouts', AdminDriverPayoutViewSet, basename='admin-payout')
router.register('admin/fleet', AdminFleetViewSet, basename='admin-fleet')
router.register('admin/reviews', AdminReviewViewSet, basename='admin-review')

urlpatterns = [
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
] + router.urls

