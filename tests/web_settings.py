import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-deployment-secret")

from cs_map_trainer.web.settings import *  # noqa: E402,F403

DEBUG = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
R2_ENDPOINT = "https://example.r2.cloudflarestorage.com"
R2_BUCKET = "test-inputs"
R2_ACCESS_KEY_ID = "test"
R2_SECRET_ACCESS_KEY = "test"
