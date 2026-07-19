from rest_framework.routers import DefaultRouter

from .views import AdminDiscountCodeViewSet

router = DefaultRouter()
router.register('admin/discounts', AdminDiscountCodeViewSet, basename='admin-discount')

urlpatterns = router.urls
