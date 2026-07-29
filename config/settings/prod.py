from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in config("ALLOWED_HOSTS", default="").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be configured in production")
CSRF_TRUSTED_ORIGINS = (
    config("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if config("CSRF_TRUSTED_ORIGINS", default="")
    else []
)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content-hashed filenames, so a stylesheet change reaches browsers on its own.
# Before this, base.html carried a hand-written `?v=` suffix that someone had to
# remember to bump; it still read "20260724-legibility2" after the CSS had been
# rewritten, which means a returning user would have kept the old file.
# WhiteNoise's variant also pre-compresses, and it is the storage WhiteNoise
# expects when serving with far-future cache headers.
#
# Only in production: the manifest is written by `collectstatic`, and requiring
# it in development would mean running collectstatic before every runserver.
#
# AeroControlStaticFilesStorage subclasses the WhiteNoise storage to disable the
# manifest URL-rewriting (`patterns = ()`): rewriting vendored CSS/JS bytes
# (e.g. source-map comments) invalidates the Subresource Integrity hashes we
# ship for `static/vendor`, so browsers reject those assets. See
# config/static_storage.py.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.static_storage.AeroControlStaticFilesStorage"},
}
