from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE_MB = 5

# Magic-byte signatures for the only extensions DOCUMENT_EXTENSIONS (FileExtensionValidator)
# allows anywhere in this codebase - pdf, jpg, jpeg, png. A renamed file (e.g. a .exe saved as
# license.pdf) passes the extension check but not this, since the actual bytes don't match.
_DOCUMENT_SIGNATURES = (b'%PDF-', b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n')


def validate_file_size(value):
    limit = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if value.size > limit:
        raise ValidationError(f'File too large ({value.size // 1024 // 1024}MB). Max size is {MAX_UPLOAD_SIZE_MB}MB.')


def validate_document_content(value):
    header = value.read(8)
    value.seek(0)
    if not header.startswith(_DOCUMENT_SIGNATURES):
        raise ValidationError('File content does not match a supported format (PDF, JPEG, or PNG).')
