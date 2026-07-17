"""Production-only settings."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


DEBUG = False

R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")  # noqa: F405
R2_PUBLIC_URL_PARTS = urlparse(R2_PUBLIC_URL)  # noqa: F405

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.getenv("R2_ACCESS_KEY_ID"),  # noqa: F405
            "secret_key": os.getenv("R2_SECRET_ACCESS_KEY"),  # noqa: F405
            "bucket_name": os.getenv("R2_BUCKET_NAME"),  # noqa: F405
            "endpoint_url": os.getenv("R2_ENDPOINT_URL"),  # noqa: F405
            "region_name": "auto",
            "custom_domain": R2_PUBLIC_URL_PARTS.netloc,
            "url_protocol": f"{R2_PUBLIC_URL_PARTS.scheme or 'https'}:",
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": False,
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = f"{R2_PUBLIC_URL}/"
THUMBNAIL_URL = os.getenv("THUMBNAIL_URL", MEDIA_URL)  # noqa: F405

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be set in production")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production")

required_r2_settings = {
    "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID"),  # noqa: F405
    "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY"),  # noqa: F405
    "R2_BUCKET_NAME": os.getenv("R2_BUCKET_NAME"),  # noqa: F405
    "R2_ENDPOINT_URL": os.getenv("R2_ENDPOINT_URL"),  # noqa: F405
    "R2_PUBLIC_URL": R2_PUBLIC_URL,
}
missing_r2_settings = [
    name for name, value in required_r2_settings.items() if not value
]
if missing_r2_settings:
    raise ImproperlyConfigured(
        "Missing Cloudflare R2 settings: " + ", ".join(missing_r2_settings)
    )
