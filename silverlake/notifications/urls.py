from rest_framework.routers import DefaultRouter

from .views import ClientNotificationViewSet, DriverNotificationViewSet, NotificationViewSet

router = DefaultRouter()
router.register('admin/notifications', NotificationViewSet, basename='admin-notification')
router.register('driver/notifications', DriverNotificationViewSet, basename='driver-notification')
router.register('notifications', ClientNotificationViewSet, basename='client-notification')

urlpatterns = router.urls
