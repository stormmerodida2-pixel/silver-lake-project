from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAuditLogViewSet,
    AdminBookingViewSet,
    AdminDriverApplicationViewSet,
    AdminDriverPayoutViewSet,
    AdminDriverViewSet,
    AdminFleetViewSet,
    AdminRefundViewSet,
    AdminReviewViewSet,
    AdminStatsView,
    AdminUserViewSet,
    AdminVehicleCategoryViewSet,
    AdminVehicleSubmissionViewSet,
)

router = DefaultRouter()
router.register('admin/users', AdminUserViewSet, basename='admin-user')
router.register('admin/drivers', AdminDriverViewSet, basename='admin-driver')
router.register('admin/driver-applications', AdminDriverApplicationViewSet, basename='admin-driver-application')
router.register('admin/bookings', AdminBookingViewSet, basename='admin-booking')
router.register('admin/payouts', AdminDriverPayoutViewSet, basename='admin-payout')
router.register('admin/refunds', AdminRefundViewSet, basename='admin-refund')
router.register('admin/fleet', AdminFleetViewSet, basename='admin-fleet')
router.register('admin/fleet-types', AdminVehicleCategoryViewSet, basename='admin-fleet-type')
router.register('admin/reviews', AdminReviewViewSet, basename='admin-review')
router.register('admin/vehicle-submissions', AdminVehicleSubmissionViewSet, basename='admin-vehicle-submission')
router.register('admin/audit-log', AdminAuditLogViewSet, basename='admin-audit-log')

urlpatterns = [
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
] + router.urls

