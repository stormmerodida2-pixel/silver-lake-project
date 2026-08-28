from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE_MB = 5


def validate_file_size(value):
    limit = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if value.size > limit:
        raise ValidationError(f'File too large ({value.size // 1024 // 1024}MB). Max size is {MAX_UPLOAD_SIZE_MB}MB.')
