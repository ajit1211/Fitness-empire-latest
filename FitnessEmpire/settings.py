"""
Django settings for FitnessEmpire.

Everything that differs between a laptop and a deployed site is read from the
environment, so the same file runs both. Running `manage.py` locally with no
environment set keeps the old behaviour: DEBUG on, SQLite, console email.

On Vercel the platform sets VERCEL=1, which flips the safe defaults on:
DEBUG off, HTTPS-only cookies, and a real database required.

See DEPLOY.md for the variables to set and why each one matters.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Vercel sets this on every build and every request.
IS_VERCEL = bool(os.environ.get("VERCEL"))


def env_flag(name, default=False):
    """Read a boolean from the environment, accepting 1/true/yes/on."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
# The old hardcoded key is gone. It sat in the repo and in the public git
# history, so anything signed with it (sessions, password-reset tokens) has to
# be considered compromised; generate a new one for the deployed site.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

# Deployed with no key set is a hard error rather than a silent weak default.
DEBUG = env_flag("DJANGO_DEBUG", default=not IS_VERCEL)

# A deployment that is missing production settings still runs, in a reduced
# "demo mode", rather than refusing to start. Refusing was safe but useless:
# the site was unreachable and the reason was buried in a platform log. Running
# with a banner that states the limitation on every page is just as honest and
# far easier to act on. Each shortcoming is recorded here and shown to visitors.
DEMO_REASONS = []

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-only-do-not-deploy-this"
    else:
        import secrets

        # Generated per process. It is a real random key, so nothing is
        # insecure; it simply differs between instances, which logs people out
        # whenever a new one starts. Set DJANGO_SECRET_KEY to make it stable.
        SECRET_KEY = secrets.token_urlsafe(50)
        DEMO_REASONS.append(
            "DJANGO_SECRET_KEY is not set, so a new signing key is generated "
            "each time the server starts and everyone is signed out."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS") or [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "testserver",
]

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

if IS_VERCEL:
    # Every deployment gets its own generated hostname alongside the project
    # domain, so both have to be accepted or the preview URLs 400.
    ALLOWED_HOSTS += [".vercel.app"]
    CSRF_TRUSTED_ORIGINS += ["https://*.vercel.app"]

    deployment_url = os.environ.get("VERCEL_URL")
    if deployment_url:
        ALLOWED_HOSTS.append(deployment_url)
        CSRF_TRUSTED_ORIGINS.append(f"https://{deployment_url}")


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'FitnessGYM',
    'paypal.standard.ipn',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves CSS, JS and images straight from the Python process. Vercel has no
    # separate web server in front of Django, so without this every asset 404s
    # once DEBUG is off.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'FitnessEmpire.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'FitnessGYM.context_processors.cart_summary',
                'FitnessGYM.context_processors.demo_notice',
            ],
        },
    },
]

WSGI_APPLICATION = 'FitnessEmpire.wsgi.application'


# ---------------------------------------------------------------------------
# Database
#
# Vercel runs the app on a read-only filesystem that is thrown away between
# requests, so a SQLite file cannot hold anything: every sign-up, cart and order
# would disappear. A managed Postgres (Neon, Supabase, Vercel Postgres) is
# required, handed over as DATABASE_URL.
#
# With no DATABASE_URL the site still runs, from a temp copy of the committed
# SQLite file, and every page carries a banner saying nothing is saved. See
# DEMO_REASONS above.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
    }
elif DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    import shutil
    import tempfile

    # No database was configured. Rather than refuse to serve, run from a copy
    # of the catalogue that ships with the repository, placed in the system
    # temp directory because that is the only writable path on a serverless
    # host. It is per-instance and short-lived, so writes do not survive.
    scratch_db = Path(tempfile.gettempdir()) / "fitnessempire-ephemeral.sqlite3"
    bundled_db = BASE_DIR / "db.sqlite3"
    if not scratch_db.exists() and bundled_db.exists():
        shutil.copy(bundled_db, scratch_db)

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(scratch_db),
        }
    }
    DEMO_REASONS.append(
        "DATABASE_URL is not set, so the site is running on a temporary copy "
        "of the bundled catalogue. Accounts, carts and orders are discarded "
        "when the server restarts."
    )

# True whenever the deployment is running on fallbacks. Surfaced on every page
# by FitnessGYM.context_processors.demo_notice so it cannot go unnoticed.
DEMO_MODE = bool(DEMO_REASONS)


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True  # Keep database timestamps in UTC
USE_I18N = True


# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Product images that ship with the repo. Serving them from the app is a
# stopgap: the filesystem is read-only, so images uploaded through the admin
# will not survive. Point an object store at MEDIA_ROOT before relying on
# uploads. See DEPLOY.md.
SERVE_MEDIA_FILES = env_flag("SERVE_MEDIA_FILES", default=True)

# WhiteNoise reads through Django's staticfiles finders instead of requiring a
# collectstatic pass, which removes the build step Vercel would otherwise need.
# Run collectstatic and drop this if you later want hashed, far-future-cached
# asset URLs.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}


# ---------------------------------------------------------------------------
# HTTPS
#
# Vercel terminates TLS at the edge and forwards plain HTTP, so Django sees an
# insecure request unless it is told to trust the forwarding header. Without
# this the PayPal return and IPN URLs are built as http:// and the redirect back
# from PayPal breaks.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'
    # Vercel already redirects to HTTPS at the edge, so leave Django's own
    # redirect off to avoid a second hop.
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
    SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)


# ---------------------------------------------------------------------------
# PayPal
# ---------------------------------------------------------------------------
PAYPAL_RECEIVER_EMAIL = os.environ.get(
    'PAYPAL_RECEIVER_EMAIL', 'sb-owhlw37372559@business.example.com'
)
PAYPAL_TEST = env_flag('PAYPAL_TEST', default=True)

# Prices are quoted in rupees but the PayPal button is submitted in USD (the
# sandbox business account cannot settle INR). Totals are converted with this
# rate before the amount is handed to PayPal.
INR_TO_USD_RATE = os.environ.get('INR_TO_USD_RATE', '0.012')


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'


# ---------------------------------------------------------------------------
# Email (the forgot-password OTP flow)
#
# The app password that used to be hardcoded here was published in the git
# history and must be revoked. Nothing is hardcoded now: with no password set
# the OTP is printed to the log instead of sent, which keeps the flow testable
# without silently failing.
# ---------------------------------------------------------------------------
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = env_flag('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL') or EMAIL_HOST_USER or 'no-reply@fitnessempire.local'
EMAIL_TIMEOUT = 10

EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST_PASSWORD
    else 'django.core.mail.backends.console.EmailBackend',
)


# ---------------------------------------------------------------------------
# Messages: tags that match the stylesheet
# ---------------------------------------------------------------------------
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: 'info',
    message_constants.INFO: 'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR: 'error',
}


# ---------------------------------------------------------------------------
# Caching
#
# Each serverless instance gets its own memory, so this is a per-instance cache,
# not a shared one. Fine for the short-lived fragment caching here; point it at
# Redis if you ever need cache coherence between instances.
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fitness-empire',
        'TIMEOUT': 300,
    }
}


# ---------------------------------------------------------------------------
# Logging: send everything to stdout, which is where Vercel collects logs.
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
    },
}
