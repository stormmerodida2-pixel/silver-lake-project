from django.core.management.base import BaseCommand

from blog.services import cleanup_orphaned_blog_images


class Command(BaseCommand):
    help = (
        "Deletes inline blog images (uploaded through the rich-text editor) that are no longer "
        "referenced by any post's body - run periodically (e.g. via cron) since nothing else "
        "cleans these up automatically."
    )

    def handle(self, *args, **options):
        count = cleanup_orphaned_blog_images()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} orphaned inline blog image(s).'))
