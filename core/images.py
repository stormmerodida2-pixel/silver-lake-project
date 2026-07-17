"""Resizes and recompresses uploaded photos before they ever reach storage - vehicle/blog/driver
photos and avatars, never compliance documents (driver licenses, logbooks, insurance certs),
which need to stay full-fidelity and legible for verification. A phone photo straight off a
modern camera easily runs 4-8MB at 4000px+ wide; nothing on this site displays a photo anywhere
near that size, so every visitor was downloading far more than they'd ever see.
"""
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

DEFAULT_MAX_DIMENSION = 1600
DEFAULT_JPEG_QUALITY = 82


def optimize_image(image_field_file, max_dimension=DEFAULT_MAX_DIMENSION, quality=DEFAULT_JPEG_QUALITY):
    """Call from a model's own save(), guarded by `not image_field_file._committed` (Django's
    own marker for "freshly assigned this request, not yet written to storage") so an
    already-optimized existing file already in storage never gets re-processed on every
    unrelated save of the same row. Resizes down only (never upscales a smaller image), converts
    to JPEG unless the source has real transparency (kept as PNG), and auto-rotates from EXIF
    orientation before stripping all EXIF - phone photos often embed GPS coordinates, so this
    doubles as a privacy improvement, not just a size one.

    Never allowed to break the upload it's called from - optimization is a nice-to-have, not a
    hard requirement, so anything Pillow can't parse (a corrupted file, an unusual format, or -
    same effective case - a test fixture using placeholder bytes rather than a real image) just
    leaves the original file exactly as uploaded instead of turning into a 500."""
    try:
        image_field_file.file.seek(0)
        img = Image.open(image_field_file.file)
        img.load()  # Image.open() is lazy - a truncated/corrupt file often only fails here
        img = ImageOps.exif_transpose(img)

        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
        buffer = BytesIO()
        if has_alpha:
            img.save(buffer, format='PNG', optimize=True)
            new_ext = 'png'
        else:
            img = img.convert('RGB')
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            new_ext = 'jpg'

        base_name = image_field_file.name.rsplit('.', 1)[0]
        image_field_file.save(f'{base_name}.{new_ext}', ContentFile(buffer.getvalue()), save=False)
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning('Could not optimize image %r, saving as-uploaded: %s', image_field_file.name, exc)
        image_field_file.file.seek(0)
