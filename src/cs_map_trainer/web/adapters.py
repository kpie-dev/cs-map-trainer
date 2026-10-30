import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import quote, urlsplit, urlunsplit

from allauth.account import app_settings as account_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.urls import reverse
from django.utils.encoding import force_str


class SupportAccountAdapter(DefaultAccountAdapter):
    def set_password(self, user, password):
        user.set_password(password)
        user.save(update_fields=["password"])

    def _support_url(self, request, url):
        if not getattr(request, "support_mail", False):
            return url
        from .billing import public_origin

        parts = urlsplit(url)
        return public_origin() + urlunsplit(("", "", parts.path, parts.query, parts.fragment))

    def get_reset_password_from_key_url(self, key):
        if not getattr(self.request, "support_mail", False):
            return super().get_reset_password_from_key_url(key)
        path = reverse(
            "account_reset_password_from_key", kwargs={"uidb36": "UID", "key": "KEY"}
        ).replace("UID-KEY", quote(key))
        return self._support_url(self.request, path)

    def get_email_confirmation_url(self, request, emailconfirmation):
        if not getattr(request, "support_mail", False):
            return super().get_email_confirmation_url(request, emailconfirmation)
        return self._support_url(
            request, reverse("account_confirm_email", args=[emailconfirmation.key])
        )

    def _support_site(self):
        from .billing import public_origin

        domain = urlsplit(public_origin()).netloc
        return SimpleNamespace(domain=domain, name=domain)

    def format_email_subject(self, subject):
        if not getattr(self.request, "support_mail", False):
            return super().format_email_subject(subject)
        prefix = account_settings.EMAIL_SUBJECT_PREFIX
        if prefix is None:
            prefix = f"[{self._support_site().name}] "
        return prefix + force_str(subject)

    def send_mail(self, template_prefix, email, context):
        if not getattr(self.request, "support_mail", False):
            return super().send_mail(template_prefix, email, context)
        mail_context = {
            **context,
            "request": self.request,
            "email": email,
            "current_site": self._support_site(),
        }
        self.render_mail(template_prefix, email, mail_context).send()


class EncryptedMFAAdapter(DefaultMFAAdapter):
    """Encrypt MFA material at rest; retain SECRET_KEY_FALLBACKS during rotation."""

    def _cipher(self):
        keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
        return MultiFernet(
            [
                Fernet(
                    base64.urlsafe_b64encode(hashlib.sha256(f"support-mfa:{key}".encode()).digest())
                )
                for key in keys
            ]
        )

    def encrypt(self, text):
        return self._cipher().encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text):
        return self._cipher().decrypt(encrypted_text.encode()).decode()
