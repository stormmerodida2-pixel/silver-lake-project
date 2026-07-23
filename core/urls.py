from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAnalyticsView,
    AdminAuditLogViewSet,
    AdminBookingViewSet,
    AdminClientErrorReportViewSet,
    AdminDriverApplicationViewSet,
    AdminDriverPayoutViewSet,
    AdminDriverViewSet,
    AdminFleetPartnerViewSet,
    AdminFleetViewSet,
    AdminHealthView,
    AdminLoyaltyTierViewSet,
    AdminReferralSettingsView,
    AdminRefundViewSet,
    AdminReviewViewSet,
    AdminStatsView,
    AdminUserViewSet,
    AdminVehicleCategoryViewSet,
    AdminVehicleSubmissionViewSet,
    ReportClientErrorView,
)

router = DefaultRouter()
router.register('admin/users', AdminUserViewSet, basename='admin-user')
router.register('admin/drivers', AdminDriverViewSet, basename='admin-driver')
router.register('admin/driver-applications', AdminDriverApplicationViewSet, basename='admin-driver-application')
router.register('admin/bookings', AdminBookingViewSet, basename='admin-booking')
router.register('admin/payouts', AdminDriverPayoutViewSet, basename='admin-payout')
router.register('admin/refunds', AdminRefundViewSet, basename='admin-refund')
router.register('admin/fleet', AdminFleetViewSet, basename='admin-fleet')
router.register('admin/fleet-partners', AdminFleetPartnerViewSet, basename='admin-fleet-partner')
router.register('admin/fleet-types', AdminVehicleCategoryViewSet, basename='admin-fleet-type')
router.register('admin/reviews', AdminReviewViewSet, basename='admin-review')
router.register('admin/vehicle-submissions', AdminVehicleSubmissionViewSet, basename='admin-vehicle-submission')
router.register('admin/audit-log', AdminAuditLogViewSet, basename='admin-audit-log')
router.register('admin/client-errors', AdminClientErrorReportViewSet, basename='admin-client-error')
router.register('admin/loyalty-tiers', AdminLoyaltyTierViewSet, basename='admin-loyalty-tier')

urlpatterns = [
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('admin/analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),
    path('admin/health/', AdminHealthView.as_view(), name='admin-health'),
    path('admin/referral-settings/', AdminReferralSettingsView.as_view(), name='admin-referral-settings'),
    path('report-client-error/', ReportClientErrorView.as_view(), name='report-client-error'),
] + router.urls
