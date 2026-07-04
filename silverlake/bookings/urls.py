from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    DriverBookingCashPaymentView,
    DriverBookingView,
    DriverOnsiteBookingCreateView,
)

router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('driver/bookings/create/', DriverOnsiteBookingCreateView.as_view(), name='driver-onsite-booking-create'),
    path('driver/bookings/<int:pk>/record-cash/', DriverBookingCashPaymentView.as_view(), name='driver-booking-record-cash'),
    path('driver/bookings/<uuid:token>/', DriverBookingView.as_view(), name='driver-booking'),
] + router.urls

