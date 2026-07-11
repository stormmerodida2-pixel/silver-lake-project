from rest_framework.routers import DefaultRouter

from .views import DriverNotificationViewSet, NotificationViewSet

router = DefaultRouter()
router.register('admin/notifications', NotificationViewSet, basename='admin-notification')
router.register('driver/notifications', DriverNotificationViewSet, basename='driver-notification')

urlpatterns = router.urls
