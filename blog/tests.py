import base64

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import StaffOrganization
from fleet.models import FleetPartner

from .models import BlogPost
from .sanitize import sanitize_body

User = get_user_model()

_PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


def _png(name):
    return SimpleUploadedFile(name, _PNG, content_type='image/png')


class SlugGenerationTests(TestCase):
    def test_slug_is_generated_from_title(self):
        post = BlogPost.objects.create(title='Kisumu Weekend Guide', excerpt='e', body='<p>b</p>')
        self.assertEqual(post.slug, 'kisumu-weekend-guide')

    def test_duplicate_titles_get_suffixed_slugs(self):
        first = BlogPost.objects.create(title='Kisumu Weekend Guide', excerpt='e', body='<p>b</p>')
        second = BlogPost.objects.create(title='Kisumu Weekend Guide', excerpt='e', body='<p>b</p>')
        third = BlogPost.objects.create(title='Kisumu Weekend Guide', excerpt='e', body='<p>b</p>')
        self.assertEqual(first.slug, 'kisumu-weekend-guide')
        self.assertEqual(second.slug, 'kisumu-weekend-guide-2')
        self.assertEqual(third.slug, 'kisumu-weekend-guide-3')

    def test_published_at_is_set_once_on_first_publish(self):
        post = BlogPost.objects.create(title='A Post', excerpt='e', body='<p>b</p>')
        self.assertIsNone(post.published_at)
        post.is_published = True
        post.save()
        first_published_at = post.published_at
        self.assertIsNotNone(first_published_at)

        post.is_published = False
        post.save()
        post.is_published = True
        post.save()
        self.assertEqual(post.published_at, first_published_at)


class SanitizeBodyTests(TestCase):
    def test_script_tag_and_its_content_are_removed(self):
        result = sanitize_body('<p>hi</p><script>alert(1)</script>')
        self.assertNotIn('<script', result)
        self.assertNotIn('alert(1)', result)
        self.assertIn('<p>hi</p>', result)

    def test_event_handler_attributes_are_stripped(self):
        result = sanitize_body('<p onclick="evil()">hi</p>')
        self.assertNotIn('onclick', result)
        self.assertIn('hi', result)

    def test_allowed_formatting_survives(self):
        result = sanitize_body('<h2>Title</h2><ul><li>one</li></ul><strong>bold</strong>')
        self.assertIn('<h2>Title</h2>', result)
        self.assertIn('<li>one</li>', result)
        self.assertIn('<strong>bold</strong>', result)


class AdminBlogPermissionTests(APITestCase):
    def setUp(self):
        self.platform_super = User.objects.create_superuser(
            username='blog-platform-super@example.com', password='pass12345!',
        )
        self.support_staff = User.objects.create_user(
            username='blog-support@example.com', password='pass12345!', is_staff=True,
        )
        org = FleetPartner.objects.create(name='Blog Org', platform_fee_percent=10)
        self.org_admin = User.objects.create_user(
            username='blog-org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_admin, organization=org)

    def _create_payload(self):
        return {'title': 'New Post', 'excerpt': 'An excerpt', 'body': '<p>body</p>'}

    def test_platform_superadmin_can_create_update_delete(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/blog/', self._create_payload(), format='multipart')
        self.assertEqual(response.status_code, 201)
        post_id = response.json()['id']

        response = self.client.patch(f'/api/admin/blog/{post_id}/', {'title': 'Updated'}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Updated')

        response = self.client.delete(f'/api/admin/blog/{post_id}/')
        self.assertEqual(response.status_code, 204)

    def test_org_admin_cannot_create_a_blog_post(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post('/api/admin/blog/', self._create_payload(), format='multipart')
        self.assertEqual(response.status_code, 403)

    def test_support_staff_cannot_access_admin_blog(self):
        self.client.force_authenticate(user=self.support_staff)
        response = self.client.post('/api/admin/blog/', self._create_payload(), format='multipart')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_access_admin_blog(self):
        response = self.client.post('/api/admin/blog/', self._create_payload(), format='multipart')
        self.assertIn(response.status_code, (401, 403))

    def test_inline_image_upload_allowed_for_platform_superadmin_only(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/blog/upload-image/', {'image': _png('inline.png')}, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertIn('image', response.json())

        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post('/api/admin/blog/upload-image/', {'image': _png('inline2.png')}, format='multipart')
        self.assertEqual(response.status_code, 403)


class PublicBlogTests(APITestCase):
    def setUp(self):
        self.published = BlogPost.objects.create(
            title='Published Post', excerpt='e', body='<p>b</p>', is_published=True,
        )
        self.draft = BlogPost.objects.create(
            title='Draft Post', excerpt='e', body='<p>b</p>', is_published=False,
        )

    def test_public_list_only_returns_published_posts(self):
        response = self.client.get('/api/blog/')
        self.assertEqual(response.status_code, 200)
        slugs = [p['slug'] for p in response.json()]
        self.assertIn(self.published.slug, slugs)
        self.assertNotIn(self.draft.slug, slugs)

    def test_public_list_orders_most_recently_published_first(self):
        newer = BlogPost.objects.create(
            title='Newer Post', excerpt='e', body='<p>b</p>', is_published=True,
        )
        response = self.client.get('/api/blog/')
        slugs = [p['slug'] for p in response.json()]
        self.assertLess(slugs.index(newer.slug), slugs.index(self.published.slug))

    def test_published_post_detail_is_reachable_by_slug(self):
        response = self.client.get(f'/api/blog/{self.published.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Published Post')

    def test_draft_post_detail_404s(self):
        response = self.client.get(f'/api/blog/{self.draft.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_404s(self):
        response = self.client.get('/api/blog/does-not-exist/')
        self.assertEqual(response.status_code, 404)


class CoverImageCleanupTests(APITestCase):
    def setUp(self):
        self.platform_super = User.objects.create_superuser(
            username='blog-cleanup-super@example.com', password='pass12345!',
        )

    def test_replacing_cover_image_deletes_the_old_file(self):
        post = BlogPost.objects.create(title='Image Post', excerpt='e', body='<p>b</p>')
        post.cover_image.save('first.png', _png('first.png'), save=True)
        old_name = post.cover_image.name
        self.assertTrue(post.cover_image.storage.exists(old_name))

        self.client.force_authenticate(user=self.platform_super)
        response = self.client.patch(
            f'/api/admin/blog/{post.id}/', {'cover_image': _png('second.png')}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertNotEqual(post.cover_image.name, old_name)
        self.assertFalse(post.cover_image.storage.exists(old_name))
