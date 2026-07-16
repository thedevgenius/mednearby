"""Production-only settings."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


DEBUG = False

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY must be set in production")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production")
