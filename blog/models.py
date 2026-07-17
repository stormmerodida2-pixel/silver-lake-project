from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.images import optimize_image


class BlogCategory(models.TextChoices):
    TRAVEL_TIPS = 'travel_tips', 'Travel Tips'
    DESTINATION_GUIDES = 'destination_guides', 'Destination Guides'
    FLEET_SPOTLIGHTS = 'fleet_spotlights', 'Fleet & Driver Spotlights'
    COMPANY_NEWS = 'company_news', 'Company News'


class BlogPost(models.Model):
    """Marketing/SEO content - travel tips, Kisumu/Kenya destination guides, fleet & driver
    spotlights. Superadmin-authored only, no staff-proposal/approval workflow (unlike
    Announcement) - is_published is a single person's own on/off switch, not a second-person
    review step."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=30, choices=BlogCategory.choices, default=BlogCategory.TRAVEL_TIPS)
    excerpt = models.CharField(
        max_length=300,
        help_text='Shown as the list-page teaser and used as the SEO meta description.',
    )
    body = models.TextField(help_text='Sanitized HTML from the rich-text editor.')
    cover_image = models.ImageField(upload_to='blog/', blank=True, null=True)
    is_published = models.BooleanField(default=False)
    # Set once, the first time is_published flips True - never reset on unpublish/republish,
    # so a temporarily-unpublished-then-republished post keeps its original public ordering
    # instead of jumping to the top again.
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # -id as a final tiebreaker: two posts published within the same clock tick (Windows'
        # timer resolution can be coarse enough for this to happen even in normal use) would
        # otherwise sort in an undefined order between themselves.
        ordering = ['-published_at', '-created_at', '-id']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        if self.cover_image and not self.cover_image._committed:
            optimize_image(self.cover_image)
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.title)[:200] or 'post'
        slug = base
        suffix = 2
        while BlogPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{suffix}'
            suffix += 1
        return slug


class BlogImageUpload(models.Model):
    """A standalone image upload for inline use inside a BlogPost's body, independent of any
    specific post - solves the chicken-and-egg problem of the rich-text editor needing to embed
    a real uploaded file before the post itself has been saved/has an ID. Not linked back to
    the post(s) that end up referencing its URL, so removing an inline image from a post's body
    does not delete this row (accepted v1 trade-off)."""

    image = models.ImageField(upload_to='blog/inline/')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            optimize_image(self.image)
        super().save(*args, **kwargs)
