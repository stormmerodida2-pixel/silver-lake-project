from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DriverApplicationCreateView,
    DriverAwayView,
    DriverMeView,
    DriverVehicleServiceRecordViewSet,
    DriverVehicleSubmissionViewSet,
    DriverViewSet,
)

router = DefaultRouter()
router.register('drivers', DriverViewSet, basename='driver')
router.register('driver/vehicle-submissions', DriverVehicleSubmissionViewSet, basename='driver-vehicle-submission')
router.register('driver/service-records', DriverVehicleServiceRecordViewSet, basename='driver-service-record')

urlpatterns = [
    path('drivers/apply/', DriverApplicationCreateView.as_view(), name='driver-application-create'),
    path('driver/me/', DriverMeView.as_view(), name='driver-me'),
    path('driver/away/', DriverAwayView.as_view(), name='driver-away'),
] + router.urls
