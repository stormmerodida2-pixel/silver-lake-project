from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    DriverBookingAcknowledgeView,
    DriverBookingCashPaymentView,
    DriverBookingListView,
    DriverBookingView,
    DriverOnsiteBookingCreateView,
)

router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('driver/bookings/mine/', DriverBookingListView.as_view(), name='driver-booking-list'),
    path('driver/bookings/create/', DriverOnsiteBookingCreateView.as_view(), name='driver-onsite-booking-create'),
    path('driver/bookings/<int:pk>/record-cash/', DriverBookingCashPaymentView.as_view(), name='driver-booking-record-cash'),
    path('driver/bookings/<int:pk>/acknowledge/', DriverBookingAcknowledgeView.as_view(), name='driver-booking-acknowledge'),
    path('driver/bookings/<uuid:token>/', DriverBookingView.as_view(), name='driver-booking'),
] + router.urls

