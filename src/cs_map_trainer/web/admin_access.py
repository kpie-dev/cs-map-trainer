"""Session-backed access gates shared by the support site and its actions."""

import time
from functools import wraps
from urllib.parse import urlencode

from allauth.account.internal.flows.login import get_authentication_records
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib.admin import AdminSite
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect


def _staff_verified(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and EmailAddress.objects.filter(user=user, email__iexact=user.email, verified=True).exists()
    )


def _mfa_records(request, max_age=None):
    """Only trust allauth proofs bound to this user and a still-present factor."""
    records = get_authentication_records(request, request.user)
    now = time.time()
    max_age = settings.SESSION_COOKIE_AGE if max_age is None else max_age
    factors = {
        (auth.pk, auth.type)
        for auth in Authenticator.objects.filter(
            user=request.user,
            type__in=[Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES],
        )
    }
    return [
        record
        for record in records
        if record.get("method") == "mfa"
        and (record.get("id"), record.get("type")) in factors
        and isinstance(record.get("at"), (int, float))
        and 0 <= now - record["at"]
        and now - record["at"] < max_age
    ]


def _redirect_to(route, next_url):
    return HttpResponseRedirect(f"{reverse(route)}?{urlencode({'next': next_url})}")


def admin_access_gate(request, *, next_url=None):
    """Return a denial/challenge response, or None when admin access is proven."""
    next_url = next_url or request.get_full_path()
    if not request.user.is_authenticated:
        return _redirect_to("account_login", next_url)
    if not _staff_verified(request.user):
        return HttpResponseForbidden("An active staff account with verified email is required.")
    if not Authenticator.objects.filter(user=request.user, type=Authenticator.Type.TOTP).exists():
        return _redirect_to("mfa_activate_totp", next_url)
    if not _mfa_records(request):
        return _redirect_to("mfa_reauthenticate", next_url)
    return None


def require_fresh_admin_auth(request):
    """Return a response or None; call before every support action's side effects.

    Both password and TOTP/recovery proof must be younger than 300 seconds.
    A challenge returns to the action's GET confirmation page, never replays POST.
    Accounts without a usable password can reauthenticate using their MFA factor.
    """
    response = admin_access_gate(request, next_url=request.path)
    if response is not None:
        return response
    max_age = settings.SUPPORT_ADMIN_REAUTHENTICATION_TIMEOUT
    now = time.time()
    if request.user.has_usable_password() and not any(
        record.get("method") == "password"
        and isinstance(record.get("at"), (int, float))
        and 0 <= now - record["at"] < max_age
        for record in get_authentication_records(request, request.user)
    ):
        return _redirect_to("account_reauthenticate", request.path)
    if not _mfa_records(request, max_age=max_age):
        return _redirect_to("mfa_reauthenticate", request.path)
    return None


require_recent_admin_authentication = require_fresh_admin_auth


class SupportAdminSite(AdminSite):
    site_header = "Account support"
    site_title = "Account support"
    index_title = "Support administration"

    def has_permission(self, request):
        return (
            _staff_verified(request.user)
            and Authenticator.objects.filter(
                user=request.user, type=Authenticator.Type.TOTP
            ).exists()
            and bool(_mfa_records(request))
        )

    def admin_view(self, view, cacheable=False):
        protected = super().admin_view(view, cacheable=False)

        @wraps(view)
        def guarded(request, *args, **kwargs):
            response = admin_access_gate(request)
            if response is not None:
                return response
            return protected(request, *args, **kwargs)

        return never_cache(csrf_protect(guarded))

    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        target = request.GET.get("next", reverse(f"{self.name}:index"))
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ) or target.split("?", 1)[0].rstrip("/") == request.path.rstrip("/"):
            target = reverse(f"{self.name}:index")
        response = admin_access_gate(request, next_url=target)
        return response if response is not None else HttpResponseRedirect(target)

    def password_change(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("account_change_password"))
