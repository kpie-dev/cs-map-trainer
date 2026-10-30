from django.contrib.auth import SESSION_KEY, get_user_model, logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils.cache import add_never_cache_headers

SESSION_VERSION_KEY = "trainer_account_session_version"


def _session_version(user_id):
    from .models import AccountPolicy

    return (
        AccountPolicy.objects.filter(owner_id=user_id)
        .values_list("session_version", flat=True)
        .first()
        or 0
    )


@receiver(user_logged_in, dispatch_uid="trainer_stamp_account_session_version")
def stamp_session_version(sender, request, user, **kwargs):
    request.session[SESSION_VERSION_KEY] = {
        "user_id": str(user.pk),
        "version": _session_version(user.pk),
    }


class AccountSessionMiddleware:
    """Revoke blocked and pre-block sessions, including legacy unstamped sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get(SESSION_KEY)
        if user_id is not None:
            active = (
                get_user_model()
                .objects.filter(pk=user_id)
                .values_list("is_active", flat=True)
                .first()
            )
            version = _session_version(user_id)
            stamp = request.session.get(SESSION_VERSION_KEY)
            current = (
                stamp is None
                and version == 0
                or isinstance(stamp, dict)
                and stamp.get("user_id") == str(user_id)
                and type(stamp.get("version")) is int
                and stamp["version"] == version
            )
            if not active or not current:
                logout(request)
                request._account_session_revoked = True
            elif stamp is None:
                request.session[SESSION_VERSION_KEY] = {"user_id": str(user_id), "version": 0}
        return self.get_response(request)


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        private = (
            request.user.is_authenticated
            or getattr(request, "_account_session_revoked", False)
            or request.path.startswith(("/accounts/", "/admin/"))
        )
        response = self.get_response(request)
        if private:
            add_never_cache_headers(response)
        return response
