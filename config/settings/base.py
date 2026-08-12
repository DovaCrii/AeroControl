from datetime import timedelta
from pathlib import Path
from decouple import config
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap5",
    "rest_framework",
    "rest_framework.authtoken",
    "axes",
    "apps.core",
    "apps.registry",
    "apps.compliance",
    "apps.operations",
    "apps.maintenance",
    "apps.workboard",
    "apps.geo",
    "apps.dashboard",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.RequestMetricsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # django-axes must sit last so it sees the fully resolved request/user and
    # can turn a locked-out login attempt into its lockout response.
    "axes.middleware.AxesMiddleware",
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
                "apps.compliance.context_processors.unresolved_alert_count",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DB_ENGINE = config("DB_ENGINE", default="sqlite3")
if DB_ENGINE in {"postgres", "postgresql"}:
    db_options = {}
    db_sslmode = config("DB_SSLMODE", default="")
    if db_sslmode:
        db_options["sslmode"] = db_sslmode
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
            "OPTIONS": db_options,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": config("DB_PATH"),
            # SQLite serialises writers. With the nightly jobs and the audit
            # middleware writing on every mutating request, the 5s default
            # timeout produced intermittent "database is locked" that the
            # middleware's except swallowed - audit events were being lost
            # silently. WAL lets readers proceed during a write; NORMAL is the
            # documented safe synchronous level under WAL.
            "OPTIONS": {
                "timeout": 20,
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA synchronous=NORMAL;"
                    "PRAGMA busy_timeout=20000;"
                ),
            },
        }
    }
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "es"
LANGUAGES = [
    ("en", _("English")),
    ("es", _("Spanish")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
# The operation runs in Chile, and this decides what "today" means everywhere:
# expiry counters, the digest, the alert horizon and the report period all read
# it. With UTC the project disagreed with the operator's calendar for four hours
# every evening. Configurable so a deployment elsewhere does not need a patch.
TIME_ZONE = config("TIME_ZONE", default="America/Santiago")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(config("DOCUMENTS_DIR", default=str(BASE_DIR / "media")))
DOCUMENTS_ROOT = Path(config("DOCUMENTS_DIR", default=str(BASE_DIR / "media")))
DOCUMENTS_STORAGE_BACKEND = config("DOCUMENTS_STORAGE_BACKEND", default="local")
DOCUMENTS_STORAGE_BUCKET = config("DOCUMENTS_STORAGE_BUCKET", default="")
DOCUMENTS_STORAGE_ENDPOINT_URL = config("DOCUMENTS_STORAGE_ENDPOINT_URL", default="")
DOCUMENTS_STORAGE_REGION = config("DOCUMENTS_STORAGE_REGION", default="")
DOCUMENTS_STORAGE_ACCESS_KEY = config("DOCUMENTS_STORAGE_ACCESS_KEY", default="")
DOCUMENTS_STORAGE_SECRET_KEY = config("DOCUMENTS_STORAGE_SECRET_KEY", default="")
DOCUMENTS_ANTIVIRUS_COMMAND = config("DOCUMENTS_ANTIVIRUS_COMMAND", default="")

# Upload limits made explicit: Django's defaults are 2.5 MB each and easy to hit
# unknowingly. FILE_UPLOAD_MAX_MEMORY_SIZE only decides when a *file* upload
# spills from memory to a temp file (documents cap at 20 MB in the form, so they
# already stream). DATA_UPLOAD_MAX_MEMORY_SIZE bounds the non-file request body,
# which is what the BLOQUE GEO plan commit uses: a JSON payload capped at 8 MB
# (see docs/dev/geo-editor-plan.md), so the limit is raised to fit it plus headroom.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Base map providers for the geo editor island (GEO-7). No API keys: OSM streets
# and Esri World Imagery, both raster/XYZ, provider-swappable via config. Names
# are English source labels (proper nouns), shown in the map's layer switcher.
# The tile host list must stay in sync with the CSP img-src in
# apps/core/middleware.py.
GEO_TILE_PROVIDERS = [
    {
        "id": "streets",
        "name": "Streets (OpenStreetMap)",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
        "maxZoom": 19,
    },
    {
        "id": "satellite",
        "name": "Satellite (Esri)",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "maxZoom": 19,
    },
]

# R8.1 (ISO 8.1 meteorological review). The project's only outgoing HTTP call,
# so it is **opt-in**: a deployment that never sets WEATHER_ENABLED keeps the
# zero-outgoing-calls property it has today. Open-Meteo needs no API key, so
# there is no credential here -- see apps/core/weather.py for why that decided
# the provider choice. The call is server-side only, so the CSP below is
# unaffected (no connect-src exception).
WEATHER_ENABLED = config("WEATHER_ENABLED", default=False, cast=bool)
WEATHER_API_URL = config(
    "WEATHER_API_URL", default="https://api.open-meteo.com/v1/forecast"
)
# Short on purpose: a slow third party must not hold a gunicorn worker.
WEATHER_TIMEOUT_SECONDS = config("WEATHER_TIMEOUT_SECONDS", default=4, cast=int)
WEATHER_CACHE_SECONDS = config("WEATHER_CACHE_SECONDS", default=3600, cast=int)

# X.4b (ADR-0002 phase 2): reading AeroLink's battery inventory. Opt-in for the
# same reason as the weather call -- with no URL configured nothing is fetched
# and the zero-outgoing-calls property holds. Both services live on the same
# VM's internal network, so this is normally a localhost URL and never crosses
# the public internet.
AEROLINK_API_URL = config("AEROLINK_API_URL", default="")
AEROLINK_API_TOKEN = config("AEROLINK_API_TOKEN", default="")
AEROLINK_TIMEOUT_SECONDS = config("AEROLINK_TIMEOUT_SECONDS", default=10, cast=int)

CSP_REPORT_ONLY = config("CSP_REPORT_ONLY", default=True, cast=bool)
# Where the browser posts CSP violation reports. Defaults to the app's own
# logging endpoint; set empty to omit the report-uri directive entirely.
CSP_REPORT_URI = config("CSP_REPORT_URI", default="/csp-report/")

# Notifications. Only variable *names* live in the repo; hosts, users and
# passwords come from the environment. With no EMAIL_HOST configured the
# console backend is used, so a misconfigured deployment prints the digest
# instead of failing or silently dropping it.
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=20, cast=int)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="aerocontrol@localhost")
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if EMAIL_HOST
        else "django.core.mail.backends.console.EmailBackend"
    ),
)
# Absolute base for links inside notification emails (no request available).
SITE_BASE_URL = config("SITE_BASE_URL", default="http://localhost:8000").rstrip("/")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # The anon rate exists for one endpoint: /api-token/ accepts unauthenticated
    # username/password pairs, and without a throttle it is an offline password
    # oracle. Authenticated traffic gets a generous ceiling that a human UI
    # never reaches but a runaway script does.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("API_THROTTLE_ANON", default="10/min"),
        "user": config("API_THROTTLE_USER", default="300/min"),
        # Scoped ceiling for the geo commit/restore endpoints (GEO-6): a human
        # editor saves a handful of times a minute; a runaway client does not.
        "geo-commit": config("API_THROTTLE_GEO_COMMIT", default="30/min"),
        # Export (GEO-10) rebuilds and zips the document; tighter than commit.
        "geo-export": config("API_THROTTLE_GEO_EXPORT", default="10/min"),
        # X.3: AeroLink resolving airframes by serial. Generous -- it is a
        # machine consumer that may look up a batch after a connectivity gap --
        # but still a ceiling, so a retry loop on their side cannot saturate
        # the operational app that shares this VM.
        "padron": config("API_THROTTLE_PADRON", default="120/min"),
    },
}
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
# V.12 session policy for shared field devices: the cookie dies when the
# browser closes, the server-side session is capped regardless of activity, and
# each request slides the expiry forward so an active user is not logged out
# mid-task. All three are env-tunable for deployments with different needs.
SESSION_EXPIRE_AT_BROWSER_CLOSE = config(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE", default=True, cast=bool
)
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=12 * 60 * 60, cast=int)
SESSION_SAVE_EVERY_REQUEST = config(
    "SESSION_SAVE_EVERY_REQUEST", default=True, cast=bool
)

# django-axes: brute-force lockout on the login form. The HTML login had no
# rate limiting (only the DRF /api-token/ endpoint did), which is acceptable
# while the app is reachable only inside the Tailscale tailnet but not once it
# is exposed to the public internet via Tailscale Funnel. All knobs are
# env-tunable so a private-only deployment can loosen or disable it.
AUTHENTICATION_BACKENDS = [
    # AxesStandaloneBackend must come first: it short-circuits a locked-out
    # attempt before the real backend ever checks the password.
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_ENABLED = config("AXES_ENABLED", default=True, cast=bool)
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME = timedelta(
    minutes=config("AXES_COOLOFF_MINUTES", default=15, cast=int)
)
AXES_RESET_ON_SUCCESS = True
# Lock on the username alone. The app sits behind the Tailscale serve/funnel
# proxy, so every request arrives from 127.0.0.1 unless X-Forwarded-For is
# trusted; keying the lockout on the client IP would either be meaningless
# (all attempts share the proxy address) or spoofable via a forged header.
# Username-only lockout stops credential brute force reliably; the cooloff and
# an admin reset bound the only downside (a targeted username being held out).
AXES_LOCKOUT_PARAMETERS = ["username"]
# Record the forwarded client address in the access log for forensics even
# though it is not part of the lockout key.
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]
# axes.W006 warns that a lockout key without 'ip_address' is weaker. That is the
# deliberate choice above (username-only): behind the proxy every request shares
# one address, so an IP key would be meaningless, and username-only additionally
# protects a targeted account from a *distributed* brute force that rotates
# source IPs. Silenced so `check --deploy` stays clean; revisit if the app ever
# fronts requests with a trustworthy per-client IP.
SILENCED_SYSTEM_CHECKS = ["axes.W006"]

X_FRAME_OPTIONS = "DENY"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"
LOG_DIR = Path(config("LOGS_DIR", default=str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_DIR / "aero_ops.log"),
            "level": "INFO",
            "formatter": "json",
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf-8",
        },
        "console": {"class": "logging.StreamHandler", "level": "INFO"},
    },
    "formatters": {
        "json": {"()": "apps.core.middleware.JsonLogFormatter"},
    },
    "loggers": {
        "aerocontrol.request": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "compliance.alerts": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        "aerocontrol.jobs": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "aerocontrol.notifications": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {"handlers": ["file", "console"], "level": "INFO"},
}
