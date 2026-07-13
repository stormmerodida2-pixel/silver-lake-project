from .models import BlogImageUpload, BlogPost


def cleanup_orphaned_blog_images():
    """Deletes any BlogImageUpload (row + file) no longer referenced by any BlogPost's body -
    an inline image inserted through the rich-text editor and later removed from the post (or
    never inserted at all) otherwise sits in storage forever, since BlogImageUpload is
    deliberately decoupled from any specific post (see its docstring in models.py). Matches by
    substring rather than an exact URL, since a stored <img src="..."> may be absolute or
    relative depending on how it was serialized - the file's own relative name always appears
    as a substring of either form."""
    all_bodies = '\n'.join(BlogPost.objects.values_list('body', flat=True))
    orphaned = [upload for upload in BlogImageUpload.objects.all() if upload.image.name not in all_bodies]
    for upload in orphaned:
        upload.image.delete(save=False)
        upload.delete()
    return len(orphaned)
