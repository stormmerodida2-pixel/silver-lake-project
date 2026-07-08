from rest_framework.routers import DefaultRouter

from .views import VehicleCategoryViewSet, VehicleViewSet

router = DefaultRouter()
router.register('vehicles', VehicleViewSet, basename='vehicle')
router.register('categories', VehicleCategoryViewSet, basename='vehicle-category')

urlpatterns = router.urls
