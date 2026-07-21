"""Settings shared by every environment."""

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parents[2]


def database_from_url(url: str) -> dict:
    """Convert a database URL into Django's database configuration format."""
    parsed = urlparse(url)
    engines = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
        "sqlite": "django.db.backends.sqlite3",
    }
    try:
        engine = engines[parsed.scheme]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported database URL scheme: {parsed.scheme!r}") from exc

    if parsed.scheme == "sqlite":
        database_path = unquote(parsed.path.lstrip("/"))
        name = BASE_DIR / database_path if database_path else BASE_DIR / "db.sqlite3"
        return {"ENGINE": engine, "NAME": name}

    config = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }
    options = dict(parse_qsl(parsed.query))
    if options:
        config["OPTIONS"] = options
    return config


SECRET_KEY = os.getenv("SECRET_KEY", "")
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
    # '*',
]
CSRF_TRUSTED_ORIGINS  = [
    host.strip() for host in os.getenv("CSRF_TRUSTED_ORIGINS ", "").split(",") if host.strip()
    # '*',
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "storages",

    "core",
    "accounts",
    "directory",
    "locations"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "med.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.dashboard_new_leads",
            ],
        },
    },
]

WSGI_APPLICATION = "med.wsgi.application"
DATABASES = {"default": database_from_url(os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"))}
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
THUMBNAIL_URL = os.getenv("THUMBNAIL_URL", MEDIA_URL)
