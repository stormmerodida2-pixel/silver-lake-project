from rest_framework import generics, permissions, viewsets
from rest_framework.parsers import FormParser, MultiPartParser

from core.audit import log_admin_action
from core.permissions import IsPlatformSuperAdmin
from core.utils import capture_replaced_files, delete_files

from .models import BlogImageUpload, BlogPost
from .serializers import AdminBlogPostSerializer, BlogImageUploadSerializer, PublicBlogPostSerializer


class AdminBlogPostViewSet(viewsets.ModelViewSet):
    """Full CRUD, platform-superadmin only - see core.permissions.IsPlatformSuperAdmin: this is
    site-wide marketing content under SilverLake's own brand, never delegated to a FleetPartner's
    own org-admin even though they're also is_superuser=True."""

    queryset = BlogPost.objects.all().select_related('created_by')
    serializer_class = AdminBlogPostSerializer
    permission_classes = [IsPlatformSuperAdmin]

    def perform_create(self, serializer):
        post = serializer.save(created_by=self.request.user)
        log_admin_action(self.request, 'blogpost.create', post)

    def perform_update(self, serializer):
        old_files = capture_replaced_files(serializer, ['cover_image'])
        post = serializer.save()
        delete_files(old_files)
        log_admin_action(self.request, 'blogpost.update', post)

    def perform_destroy(self, instance):
        log_admin_action(self.request, 'blogpost.delete', instance)
        instance.delete()


class BlogImageUploadView(generics.CreateAPIView):
    """Standalone inline-image upload for the rich-text editor toolbar - independent of any
    specific post, usable before the post itself has ever been saved."""

    queryset = BlogImageUpload.objects.all()
    serializer_class = BlogImageUploadSerializer
    permission_classes = [IsPlatformSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class PublicBlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    """Public, published-only. Routed by slug, not id, for SEO-friendly URLs."""

    queryset = BlogPost.objects.filter(is_published=True)
    serializer_class = PublicBlogPostSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    lookup_field = 'slug'
