from .base import *

DEBUG = False
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="").split(",") if config("CSRF_TRUSTED_ORIGINS", default="") else []
