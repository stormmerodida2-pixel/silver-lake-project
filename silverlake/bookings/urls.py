from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, DriverBookingView

router = DefaultRouter()
router.register('bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('driver/bookings/<uuid:token>/', DriverBookingView.as_view(), name='driver-booking'),
] + router.urls

