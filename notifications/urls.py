from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientNotificationViewSet,
    DriverNotificationViewSet,
    NotificationViewSet,
    PushSubscriptionView,
    PushVapidPublicKeyView,
)

router = DefaultRouter()
router.register('admin/notifications', NotificationViewSet, basename='admin-notification')
router.register('driver/notifications', DriverNotificationViewSet, basename='driver-notification')
router.register('notifications', ClientNotificationViewSet, basename='client-notification')

urlpatterns = [
    path('push/vapid-public-key/', PushVapidPublicKeyView.as_view(), name='push-vapid-public-key'),
    path('push/subscription/', PushSubscriptionView.as_view(), name='push-subscription'),
] + router.urls
