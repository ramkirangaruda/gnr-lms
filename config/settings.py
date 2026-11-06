"""GNR Robotics LMS settings. All deployment-specific values come from env vars."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(env(key, default)).lower() in ("1", "true", "yes", "on")


# Debug is ON for local SQLite development and OFF by default once a real database is configured.
DEBUG = env_bool("DJANGO_DEBUG", not env("POSTGRES_DB"))
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY in production (.env)")
# Production must list its real hostname(s); "*" is only a convenience for local DEBUG runs.
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise RuntimeError("Set DJANGO_ALLOWED_HOSTS in production (.env), e.g. lms.example.com")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "courses",
    "portal",
]
if env("AWS_STORAGE_BUCKET_NAME"):
    INSTALLED_APPS.append("storages")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "portal.context_processors.nav_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: PostgreSQL in production (DATABASE_URL-style parts), SQLite for local dev.
if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,  # persistent connections for concurrency
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # every password people choose
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "accounts.hashers.TemporaryPasswordHasher",  # auto-generated first passwords only, see accounts/hashers.py
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
# Failed-login throttle (accounts/throttle.py): after this many failures in LOGIN_LOCKOUT_SECONDS, wait.
LOGIN_FAILS_PER_USER = int(env("LOGIN_FAILS_PER_USER", 10))
LOGIN_FAILS_PER_IP = int(env("LOGIN_FAILS_PER_IP", 100))  # a whole school lab can share one IP
LOGIN_LOCKOUT_SECONDS = int(env("LOGIN_LOCKOUT_SECONDS", 15 * 60))
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))
# Behind Caddy, Django only checks permission and Caddy sends the file (X-Accel-Redirect, see deploy/Caddyfile).
MEDIA_ACCEL_REDIRECT = env_bool("MEDIA_ACCEL_REDIRECT", False)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG
                    else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Switch uploads (videos, images) to S3 just by setting these env vars.
if env("AWS_STORAGE_BUCKET_NAME"):
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", "ap-south-1")
    AWS_QUERYSTRING_AUTH = True
    AWS_DEFAULT_ACL = None

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # bigger files stream to disk

# Cache: Redis if available (recommended for >1 app server), otherwise local memory.
if env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Send errors (with tracebacks) to the container log, so `docker compose logs web` shows why a page failed.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False}},
}

# ---- Being told when something breaks ----
# DJANGO_ADMINS="Ram <ram@example.com>, ops@example.com": every server error (500) is emailed there (needs EMAIL_HOST).
ADMINS = []
for _a in filter(None, (x.strip() for x in env("DJANGO_ADMINS", "").split(","))):
    _name, _, _mail = _a.rpartition("<")
    ADMINS.append((_name.strip() or _a, _mail.rstrip(">").strip() or _a))
if ADMINS:
    LOGGING["handlers"]["mail_admins"] = {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"}
    LOGGING["loggers"]["django.request"] = {"handlers": ["console", "mail_admins"], "level": "ERROR", "propagate": False}
# SENTRY_DSN (free tier at sentry.io): errors with full tracebacks, grouped, with email/phone alerts.
if env("SENTRY_DSN"):
    import sentry_sdk
    sentry_sdk.init(dsn=env("SENTRY_DSN"), send_default_pii=False, traces_sample_rate=0.0,
                    environment=env("SENTRY_ENVIRONMENT", "production"))

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ---- Email (only used for "Forgot password?" links) ----
# With no EMAIL_HOST, emails are printed to the console/log instead of sent (fine for local development).
# See README → "Email for password resets" for cheap SMTP providers.
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", 587))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)   # STARTTLS on port 587
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)  # implicit TLS on port 465 (set EMAIL_USE_TLS=0 then)
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", 15))
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
                    else "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "GNR Robotics LMS <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Self-service reset by email is offered when SMTP is configured (always in DEBUG, where mail goes to the console).
# Users without an email address are always reset by their instructor / school coordinator instead.
PASSWORD_RESET_BY_EMAIL = env_bool("PASSWORD_RESET_BY_EMAIL", bool(EMAIL_HOST) or DEBUG)
PASSWORD_RESET_TIMEOUT = int(env("PASSWORD_RESET_TIMEOUT", 24 * 3600))  # reset links expire after 1 day
PASSWORD_RESET_EMAILS_PER_HOUR = int(env("PASSWORD_RESET_EMAILS_PER_HOUR", 3))  # per account, stops mailbox spam

# Bunny Stream lesson videos (optional). Leave empty to hide the "Upload to Bunny" option.
# Library ID + API key: Bunny dashboard → Stream → your library → API. Token key: Security → Embed view token authentication.
BUNNY_STREAM_LIBRARY_ID = env("BUNNY_STREAM_LIBRARY_ID", "")
BUNNY_STREAM_API_KEY = env("BUNNY_STREAM_API_KEY", "")
BUNNY_STREAM_TOKEN_KEY = env("BUNNY_STREAM_TOKEN_KEY", "")
BUNNY_STREAM_EMBED_TTL = int(env("BUNNY_STREAM_EMBED_TTL", 4 * 3600))  # how long a signed player link stays valid
BUNNY_STREAM_UPLOAD_TTL = int(env("BUNNY_STREAM_UPLOAD_TTL", 6 * 3600))  # how long an instructor has to finish an upload
