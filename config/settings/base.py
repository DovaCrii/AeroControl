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
    "apps.core",
    "apps.registry",
    "apps.compliance",
    "apps.operations",
    "apps.maintenance",
    "apps.workboard",
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
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": config("DB_PATH")}
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
TIME_ZONE = "UTC"
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
CSP_REPORT_ONLY = config("CSP_REPORT_ONLY", default=True, cast=bool)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
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
        "aerocontrol.request": {"handlers": ["file", "console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["file", "console"], "level": "INFO"},
}
