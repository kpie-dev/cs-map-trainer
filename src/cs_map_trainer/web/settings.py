import os
from pathlib import Path

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
ROOT_URLCONF = "cs_map_trainer.web.urls"
WSGI_APPLICATION = "cs_map_trainer.web.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.mfa",
    "django_q",
    "cs_map_trainer.web.apps.TrainerConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "cs_map_trainer.web.middleware.AccountSessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "cs_map_trainer.web.middleware.PrivateResponseMiddleware",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "trainer"),
        "USER": os.environ.get("PGUSER", "trainer"),
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", "127.0.0.1"),
        "PORT": os.environ.get("PGPORT", "5432"),
    }
}
CACHES = {
    "default": {
        "BACKEND": "cs_map_trainer.web.auth_cache.SharedAuthenticationCache",
        "LOCATION": "trainer_shared_cache",
    }
}
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [Path(__file__).parent / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cs_map_trainer.web.presentation.ui_context",
            ]
        },
    }
]
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ALLAUTH_TRUSTED_PROXY_COUNT = 1 if os.environ.get("DJANGO_TRUST_PROXY") == "1" else 0
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = None
ACCOUNT_ADAPTER = "cs_map_trainer.web.adapters.SupportAccountAdapter"
MFA_ADAPTER = "cs_map_trainer.web.adapters.EncryptedMFAAdapter"
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_ALLOW_UNVERIFIED_EMAIL = False
MFA_TRUST_ENABLED = False
MFA_RECOVERY_CODES_SHOW_ONCE = True
MFA_TOTP_ISSUER = "CS Map Trainer"
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
SUPPORT_ADMIN_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_RATE_LIMITS = {
    "login": "30/m/ip",
    "login_failed": "10/m/ip,5/5m/key",
    "reauthenticate": "10/m/ip,5/5m/user",
}
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/history/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]
USE_I18N = False
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "trainer@localhost")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if os.environ.get("DJANGO_TRUST_PROXY") == "1" else None
)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")))
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", "/app/static"))
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
USE_TZ = True
TIME_ZONE = "UTC"
DATA_UPLOAD_MAX_MEMORY_SIZE = 16384
FILE_UPLOAD_MAX_MEMORY_SIZE = 0

R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_PUBLIC_ENDPOINT = os.environ.get("R2_PUBLIC_ENDPOINT", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
UPLOAD_URL_SECONDS = 900
UPLOAD_EXPIRE_SECONDS = 86400
DEMO_MONTHLY_LIMIT = 3
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PORTAL_CONFIGURATION_ID = os.environ.get("STRIPE_PORTAL_CONFIGURATION_ID", "")
PARSER_TIMEOUT_SECONDS = int(os.environ.get("PARSER_TIMEOUT_SECONDS", "300"))
PARSER_MEMORY_BYTES = int(os.environ.get("PARSER_MEMORY_BYTES", str(4 * 1024**3)))
WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/tmp/cmt-work"))
JOB_LEASE_SECONDS = 900
if not 1 <= PARSER_TIMEOUT_SECONDS <= 300:
    raise ValueError("PARSER_TIMEOUT_SECONDS must be between 1 and 300 for the worker lease")
if PARSER_MEMORY_BYTES < 512 * 1024**2:
    raise ValueError("PARSER_MEMORY_BYTES must be at least 512 MiB")
Q_CLUSTER = {
    "name": "trainer",
    "orm": "default",
    "workers": 1,
    "timeout": 720,
    "retry": 1800,
    "queue_limit": 1,
    "bulk": 1,
    "max_attempts": 1,
    "ack_failures": True,
    "recycle": 20,
}
