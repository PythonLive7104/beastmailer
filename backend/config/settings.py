"""Django settings for the BeastMailer Auto-Reply backend."""
from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

# Fernet key used to encrypt mailbox passwords at rest. Set MAIL_ENCRYPTION_KEY
# in .env for a stable value in production (see apps/mailboxes/crypto.py).
ENCRYPTION_KEY = os.getenv("MAIL_ENCRYPTION_KEY", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "apps.accounts",
    "apps.workspaces",
    "apps.mailboxes",
    "apps.proxies",
    "apps.rules",
    "apps.mail",
    "apps.automation",
    "apps.core",
    "apps.links",
    "apps.attachments",
    "apps.notifications",
    "apps.security",
    "apps.billing",
    "apps.campaigns",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Postgres when DATABASE_URL is set (the deployed server), SQLite otherwise (local dev).
# The URL points at localhost, so the database runs on the same machine as the app and
# is never exposed to the network:
#   postgresql://user:password@localhost:5432/dbname
#
# conn_max_age reuses the connection: run_engine ticks forever and would otherwise
# reconnect on every pass.
if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

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

STATIC_URL = "static/"
# collectstatic drops admin/DRF assets here; nginx serves the directory in production.
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Behind nginx, Django only sees the proxied request; trust the forwarded scheme so
# admin logins over HTTPS pass CSRF origin checks.
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    # Token only. The SPA authenticates with `Authorization: Token …`; it never
    # uses session cookies. Keeping SessionAuthentication here made DRF enforce
    # CSRF on API calls whenever a stray Django `sessionid` cookie was present
    # (e.g. after logging into /admin/), returning 403 "CSRF Failed" on login and
    # register. The Django admin keeps its own session + CSRF handling separately.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    # Everything requires a logged-in user by default; public endpoints opt out
    # with @permission_classes([AllowAny]).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

# During dev, allow the Vite frontend to call the API.
# Public origin used to build tracking URLs (open pixel, click redirect,
# unsubscribe) from inside the engine, which has no request to derive them from.
# Must be the address recipients can actually reach, e.g. https://your-domain.com.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5290")

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5290,http://127.0.0.1:5290"
).split(",")


'''
UPDATING SERVER FROM LOCAL

rsync -az --delete   --exclude '.git/' --exclude 'frontend/node_modules/' --exclude 'frontend/dist/'   --exclude 'backend/venv/' --exclude '**/__pycache__/' --exclude '*.pyc'   --exclude 'backend/db.sqlite3' --exclude 'backend/.env'   --exclude 'backend/media/' --exclude 'backend/staticfiles/'   ./ root@153.75.230.32:/root/client_sender/
'''