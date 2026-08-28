from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

ALLOWED_UPLOAD_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "webp", "txt")

validate_upload_extension = FileExtensionValidator(allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS)


def validate_upload_size(upload):
    from django.conf import settings

    max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
    if upload.size > max_bytes:
        raise ValidationError(
            f"File too large. Maximum size is {max_bytes // (1024 * 1024)} MB.",
            code="file_too_large",
        )
