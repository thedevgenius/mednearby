"""Development-only settings."""

from .base import *  # noqa: F403


DEBUG = True

# Safe fallback for local development only.
if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "django-insecure-development-only-key"

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")  # noqa: F405
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")  # noqa: F405
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")  # noqa: F405
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")  # noqa: F405
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")  # noqa: F405

R2_IS_CONFIGURED = all(
    (
        R2_ACCESS_KEY_ID,
        R2_SECRET_ACCESS_KEY,
        R2_BUCKET_NAME,
        R2_ENDPOINT_URL,
        R2_PUBLIC_URL,
    )
)

if R2_IS_CONFIGURED:
    r2_public_url_parts = urlparse(R2_PUBLIC_URL)  # noqa: F405
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": R2_ACCESS_KEY_ID,
                "secret_key": R2_SECRET_ACCESS_KEY,
                "bucket_name": R2_BUCKET_NAME,
                "endpoint_url": R2_ENDPOINT_URL,
                "region_name": "auto",
                "custom_domain": r2_public_url_parts.netloc,
                "url_protocol": f"{r2_public_url_parts.scheme or 'https'}:",
                "default_acl": None,
                "file_overwrite": False,
                "querystring_auth": False,
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    MEDIA_URL = f"{R2_PUBLIC_URL}/"
    THUMBNAIL_URL = os.getenv("THUMBNAIL_URL", MEDIA_URL)  # noqa: F405
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
