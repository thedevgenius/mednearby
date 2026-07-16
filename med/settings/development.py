"""Development-only settings."""

from .base import *  # noqa: F403


DEBUG = True

# Safe fallback for local development only.
if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "django-insecure-development-only-key"
