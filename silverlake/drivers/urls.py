from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DriverApplicationCreateView, DriverViewSet

router = DefaultRouter()
router.register('drivers', DriverViewSet, basename='driver')

urlpatterns = [
    path('drivers/apply/', DriverApplicationCreateView.as_view(), name='driver-application-create'),
] + router.urls
