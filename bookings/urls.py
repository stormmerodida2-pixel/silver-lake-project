from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    DriverBookingAcknowledgeView,
    DriverBookingCompleteView,
    DriverBookingEndTripView,
    DriverBookingListView,
    DriverBookingLocationView,
    DriverBookingStartTripView,
    DriverCashDepositView,
    DriverConfirmPaymentView,
    DriverDeclarePaymentView,
    DriverOnsiteBookingCreateView,
)

router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('driver/bookings/mine/', DriverBookingListView.as_view(), name='driver-booking-list'),
    path('driver/bookings/create/', DriverOnsiteBookingCreateView.as_view(), name='driver-onsite-booking-create'),
    path('driver/bookings/<int:pk>/declare-payment/', DriverDeclarePaymentView.as_view(), name='driver-booking-declare-payment'),
    path('driver/payments/<int:payment_id>/confirm/', DriverConfirmPaymentView.as_view(), name='driver-payment-confirm'),
    path('driver/payments/<int:payment_id>/deposit/', DriverCashDepositView.as_view(), name='driver-payment-deposit'),
    path('driver/bookings/<int:pk>/acknowledge/', DriverBookingAcknowledgeView.as_view(), name='driver-booking-acknowledge'),
    path('driver/bookings/<int:pk>/start-trip/', DriverBookingStartTripView.as_view(), name='driver-booking-start-trip'),
    path('driver/bookings/<int:pk>/end-trip/', DriverBookingEndTripView.as_view(), name='driver-booking-end-trip'),
    path('driver/bookings/<int:pk>/complete/', DriverBookingCompleteView.as_view(), name='driver-booking-complete'),
    path('driver/bookings/<int:pk>/location/', DriverBookingLocationView.as_view(), name='driver-booking-location'),
] + router.urls

