from .base import *

DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in config("ALLOWED_HOSTS", default="").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = (
    config("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if config("CSRF_TRUSTED_ORIGINS", default="")
    else []
)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
