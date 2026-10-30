import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.internal.flows.login import record_authentication
from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
)
from cryptography.fernet import InvalidToken
from django.contrib.auth import SESSION_KEY, get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import close_old_connections
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory
from django.urls import include, path, reverse

from cs_map_trainer.web.adapters import EncryptedMFAAdapter, SupportAccountAdapter
from cs_map_trainer.web.admin_access import SupportAdminSite, require_fresh_admin_auth
from cs_map_trainer.web.auth_cache import SharedAuthenticationCache
from cs_map_trainer.web.middleware import SESSION_VERSION_KEY
from cs_map_trainer.web.models import AccountPolicy

pytestmark = pytest.mark.django_db

site = SupportAdminSite(name="admin")
site.register(AccountPolicy)


def session_probe(request):
    return JsonResponse({"user": request.user.pk if request.user.is_authenticated else None})


def support_action(request):
    response = require_fresh_admin_auth(request)
    if response is not None:
        return response
    return HttpResponse("Confirmed action" if request.method == "POST" else "Confirm action")


urlpatterns = [
    path("", session_probe, name="home"),
    path("history/", session_probe, name="history"),
    path("practice/", session_probe, name="practice"),
    path("account/", session_probe, name="account"),
    path("admin/", site.urls),
    path("support-action/", site.admin_view(support_action)),
    path("session-probe/", session_probe),
    path("accounts/2fa/", include("allauth.mfa.urls")),
    path("accounts/", include("allauth.account.urls")),
]


@pytest.fixture(autouse=True)
def access_settings(settings):
    settings.ROOT_URLCONF = __name__
    cache.clear()


@pytest.fixture
def staff(user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def factor(staff):
    return TOTP.activate(staff, generate_totp_secret()).instance


def prove(client, user, factor, *, age=0, password=True):
    session = client.session
    request = RequestFactory().get("/")
    request.session = session
    request.user = user
    if password:
        record_authentication(request, user, "password")
    record_authentication(request, user, "mfa", id=factor.pk, type=factor.type)
    records = session["account_authentication_methods"]
    for record in records:
        record["at"] = time.time() - age
    session["account_authentication_methods"] = records
    session.save()


def test_anonymous_login_is_allauth_even_when_posting_admin_credentials(client):
    for response in [
        client.get("/admin/"),
        client.get("/admin/login/"),
        client.post("/admin/login/", {"username": "admin", "password": "anything"}),
    ]:
        assert response.status_code == 302
        assert urlsplit(response.url).path == reverse("account_login")
        assert "no-store" in response["Cache-Control"]
    assert SESSION_KEY not in client.session


@pytest.mark.parametrize("role", ["ordinary", "inactive", "unverified", "stale_email"])
def test_global_admin_gate_denies_ineligible_accounts(client, staff, factor, role):
    if role == "ordinary":
        staff.is_staff = False
    elif role == "inactive":
        staff.is_active = False
    elif role == "unverified":
        EmailAddress.objects.filter(user=staff).update(verified=False)
    else:
        staff.email = "unverified-new-address@example.test"
    staff.save()
    client.force_login(staff)
    prove(client, staff, factor)
    response = client.get("/admin/")
    assert response.status_code == (302 if role == "inactive" else 403)


def test_no_mfa_allows_only_enrollment(client, staff):
    client.force_login(staff)
    response = client.get("/admin/")
    assert urlsplit(response.url).path == reverse("mfa_activate_totp")
    response = client.get("/admin/trainer/accountpolicy/")
    assert urlsplit(response.url).path == reverse("mfa_activate_totp")
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("superuser", [False, True])
def test_enrollment_and_password_alone_do_not_prove_mfa(client, staff, factor, superuser):
    staff.is_superuser = superuser
    staff.save(update_fields=["is_superuser"])
    client.force_login(staff)
    response = client.get("/admin/")
    assert urlsplit(response.url).path == reverse("mfa_reauthenticate")
    response = client.get("/admin/login/?next=/admin/trainer/accountpolicy/")
    assert urlsplit(response.url).path == reverse("mfa_reauthenticate")


def test_mfa_proof_is_bound_to_user_and_live_authenticator(client, staff, factor):
    client.force_login(staff)
    prove(client, staff, factor)
    assert client.get("/admin/").status_code == 200
    session = client.session
    session["account_authentication_methods_user"] = "999999"
    session.save()
    assert urlsplit(client.get("/admin/").url).path == reverse("mfa_reauthenticate")
    prove(client, staff, factor)
    factor.delete()
    assert urlsplit(client.get("/admin/").url).path == reverse("mfa_activate_totp")


def test_staff_without_model_permission_cannot_read_models(client, staff, factor):
    client.force_login(staff)
    prove(client, staff, factor)
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/trainer/accountpolicy/").status_code == 403


@pytest.mark.parametrize("method", ["totp", "recovery_codes"])
def test_real_allauth_login_requires_and_records_second_factor(client, staff, method):
    secret = generate_totp_secret()
    totp = TOTP.activate(staff, secret)
    assert totp.instance.data["secret"] != secret
    if method == "recovery_codes":
        code = RecoveryCodes.activate(staff).generate_codes()[0]
    else:
        code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    response = client.post(
        reverse("account_login"), {"login": staff.email, "password": "some-password"}
    )
    assert response.status_code == 302
    assert urlsplit(response.url).path == reverse("mfa_authenticate")
    assert SESSION_KEY not in client.session
    response = client.post(reverse("mfa_authenticate"), {"code": code})
    assert response.status_code == 302
    assert client.session[SESSION_KEY] == str(staff.pk)
    assert client.session[SESSION_VERSION_KEY]["version"] == 0
    assert client.get("/admin/").status_code == 200


def test_fresh_action_requires_recent_password_and_mfa_and_does_not_replay_post(
    client, staff, factor
):
    client.force_login(staff)
    prove(client, staff, factor, age=301)
    response = client.post("/support-action/", {"reason": "must not replay"})
    assert urlsplit(response.url).path == reverse("account_reauthenticate")
    assert parse_qs(urlsplit(response.url).query)["next"] == ["/support-action/"]
    response = client.post(
        reverse("account_reauthenticate") + "?next=/support-action/",
        {"password": "some-password"},
    )
    assert response.status_code == 302
    response = client.get("/support-action/")
    assert urlsplit(response.url).path == reverse("mfa_reauthenticate")
    secret = EncryptedMFAAdapter().decrypt(factor.data["secret"])
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    response = client.post(reverse("mfa_reauthenticate") + "?next=/support-action/", {"code": code})
    assert response.status_code == 302
    response = client.get("/support-action/")
    assert response.content == b"Confirm action"
    assert client.post("/support-action/").content == b"Confirmed action"
    assert "account_reauthentication_state" not in client.session


def test_recent_password_alone_cannot_bypass_fresh_mfa(client, staff, factor):
    client.force_login(staff)
    prove(client, staff, factor, age=301)
    request = RequestFactory().get("/")
    request.session = client.session
    record_authentication(request, staff, "password", reauthenticated=True)
    request.session.save()
    response = client.post("/support-action/")
    assert urlsplit(response.url).path == reverse("mfa_reauthenticate")


@pytest.mark.parametrize("login_on_reset", [False, True])
def test_password_reset_does_not_remove_or_bypass_mfa(
    client, staff, factor, settings, login_on_reset
):
    from allauth.account.forms import default_token_generator
    from allauth.account.utils import user_pk_to_url_str

    settings.ACCOUNT_LOGIN_ON_PASSWORD_RESET = login_on_reset
    response = client.get(
        reverse(
            "account_reset_password_from_key",
            kwargs={
                "uidb36": user_pk_to_url_str(staff),
                "key": default_token_generator.make_token(staff),
            },
        )
    )
    assert response.status_code == 302
    response = client.post(
        response.url,
        {"password1": "a-new-unique-password-9843", "password2": "a-new-unique-password-9843"},
    )
    assert response.status_code == 302
    assert Authenticator.objects.filter(pk=factor.pk).exists()
    staff.refresh_from_db()
    assert staff.check_password("a-new-unique-password-9843")
    assert client.get("/admin/").status_code == 302
    if login_on_reset:
        assert urlsplit(response.url).path == reverse("mfa_authenticate")
    else:
        response = client.post(
            reverse("account_login"),
            {"login": staff.email, "password": "a-new-unique-password-9843"},
        )
        assert urlsplit(response.url).path == reverse("mfa_authenticate")
    assert SESSION_KEY not in client.session


def test_admin_login_rejects_external_next(client, staff, factor):
    client.force_login(staff)
    prove(client, staff, factor)
    assert client.get("/admin/login/?next=https://evil.example/").url == "/admin/"


def test_admin_gate_preserves_csrf(client, staff, factor):
    client.handler.enforce_csrf_checks = True
    client.force_login(staff)
    prove(client, staff, factor)
    assert client.post("/support-action/").status_code == 403


def test_mfa_reauthentication_rate_limit_cannot_be_bypassed_with_proxy_headers(
    client, staff, factor, settings
):
    settings.ACCOUNT_RATE_LIMITS = {"reauthenticate": "2/m/user"}
    client.force_login(staff)
    for index in range(2):
        response = client.post(
            reverse("mfa_reauthenticate"),
            {"code": "invalid-code"},
            HTTP_X_FORWARDED_FOR=f"192.0.2.{index + 1}",
        )
        assert response.status_code == 200
    response = client.post(
        reverse("mfa_reauthenticate"),
        {"code": "invalid-code"},
        HTTP_X_FORWARDED_FOR="192.0.2.3",
    )
    assert response.status_code == 429
    assert "no-store" in response["Cache-Control"]
    assert urlsplit(client.get("/admin/").url).path == reverse("mfa_reauthenticate")


def test_allauth_ignores_untrusted_client_ip_headers(settings):
    from allauth.core.internal.httpkit import get_client_ip

    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 0
    request = RequestFactory().get(
        "/", REMOTE_ADDR="192.0.2.5", HTTP_X_FORWARDED_FOR="192.0.2.9", HTTP_X_REAL_IP="192.0.2.10"
    )
    assert get_client_ip(request) == "192.0.2.5"


def test_allauth_trusts_only_the_client_address_added_by_caddy(settings):
    from allauth.core.internal.httpkit import get_client_ip

    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="172.18.0.5",
        HTTP_X_FORWARDED_FOR="203.0.113.200, 198.51.100.10",
        HTTP_X_REAL_IP="203.0.113.201",
    )
    assert get_client_ip(request) == "198.51.100.10"


def test_proxied_operators_do_not_share_reauthentication_ip_bucket(settings):
    from allauth.account import app_settings
    from allauth.core.internal import ratelimit
    from allauth.core.internal.httpkit import get_client_ip

    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1
    requests = []
    for index in range(6):
        actor = get_user_model().objects.create_user(
            f"reauth{index}", f"reauth{index}@example.test", "some-password"
        )
        request = RequestFactory().post(
            "/",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR=f"203.0.113.200, 198.51.100.{index + 1}",
        )
        request.user = actor
        requests.append(request)
        # Password and MFA each consume the same reauthentication policy.
        for _ in range(2):
            assert ratelimit.consume(
                request,
                app="allauth.account",
                action="reauthenticate",
                config=app_settings.RATE_LIMITS,
            )
    assert len({get_client_ip(request) for request in requests}) == 6
    for _ in range(3):
        assert ratelimit.consume(
            requests[0],
            app="allauth.account",
            action="reauthenticate",
            config=app_settings.RATE_LIMITS,
        )
    assert not ratelimit.consume(
        requests[0],
        app="allauth.account",
        action="reauthenticate",
        config=app_settings.RATE_LIMITS,
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_block_unblock_revokes_existing_sessions_permanently(client, user, legacy):
    client.force_login(user)
    if legacy:
        session = client.session
        del session[SESSION_VERSION_KEY]
        session.save()
    AccountPolicy.objects.create(owner=user, session_version=1)
    get_user_model().objects.filter(pk=user.pk).update(is_active=False)
    get_user_model().objects.filter(pk=user.pk).update(is_active=True)
    assert client.get("/session-probe/").json()["user"] is None
    assert SESSION_KEY not in client.session
    client.force_login(user)
    assert client.get("/session-probe/").json()["user"] == user.pk
    assert client.session[SESSION_VERSION_KEY]["version"] == 1


def test_blocked_session_is_flushed_even_when_auth_backend_returns_anonymous(client, user):
    client.force_login(user)
    get_user_model().objects.filter(pk=user.pk).update(is_active=False)
    response = client.get("/session-probe/")
    assert response.json()["user"] is None
    assert "no-store" in response["Cache-Control"]
    assert SESSION_KEY not in client.session


@pytest.mark.parametrize("with_policy", [False, True])
def test_legacy_sessions_only_survive_with_zero_version(client, user, with_policy):
    if with_policy:
        AccountPolicy.objects.create(owner=user)
    client.force_login(user)
    session = client.session
    del session[SESSION_VERSION_KEY]
    session.save()
    assert client.get("/session-probe/").json()["user"] == user.pk
    assert client.session[SESSION_VERSION_KEY] == {"user_id": str(user.pk), "version": 0}


@pytest.mark.parametrize(
    "stamp", [1, {}, {"user_id": "someone_else", "version": 0}, {"version": False}]
)
def test_invalid_session_version_stamps_are_rejected(client, user, stamp):
    client.force_login(user)
    session = client.session
    session[SESSION_VERSION_KEY] = stamp
    session.save()
    assert client.get("/session-probe/").json()["user"] is None


def test_mfa_encryption_supports_secret_key_rotation(settings):
    adapter = EncryptedMFAAdapter()
    ciphertext = adapter.encrypt("test secret material")
    assert "test secret material" not in ciphertext
    old_key = settings.SECRET_KEY
    settings.SECRET_KEY = "rotated-test-key"
    settings.SECRET_KEY_FALLBACKS = [old_key]
    assert adapter.decrypt(ciphertext) == "test secret material"
    rotated = adapter.encrypt("new material")
    settings.SECRET_KEY_FALLBACKS = []
    assert adapter.decrypt(rotated) == "new material"
    with pytest.raises(InvalidToken):
        adapter.decrypt(ciphertext)


@pytest.mark.parametrize("support_mail", [False, True])
def test_support_email_links_use_trusted_origin_only_for_support(settings, support_mail):
    settings.PUBLIC_BASE_URL = "https://trainer.example"
    request = RequestFactory().get("/")
    request.support_mail = support_mail
    untrusted = "http://untrusted.example/accounts/confirm-email/token/?key=value"
    result = SupportAccountAdapter()._support_url(request, untrusted)
    assert result == (
        "https://trainer.example/accounts/confirm-email/token/?key=value"
        if support_mail
        else untrusted
    )


@pytest.mark.parametrize("support_mail", [False, True])
def test_allauth_adapter_hooks_keep_paths_and_keys(settings, user, support_mail):
    from allauth.account.models import EmailConfirmationHMAC

    settings.PUBLIC_BASE_URL = "https://trainer.example"
    request = RequestFactory().get("/")
    request.support_mail = support_mail
    email = EmailAddress.objects.get(user=user)
    confirmation = EmailConfirmationHMAC(email)
    with context.request_context(request):
        adapter = SupportAccountAdapter()
        reset_url = adapter.get_reset_password_from_key_url("uid-token")
        verify_url = adapter.get_email_confirmation_url(request, confirmation)
    expected_origin = "https://trainer.example" if support_mail else "http://testserver"
    assert reset_url == expected_origin + reverse(
        "account_reset_password_from_key", kwargs={"uidb36": "uid", "key": "token"}
    )
    assert verify_url == expected_origin + reverse("account_confirm_email", args=[confirmation.key])


def test_support_mail_never_uses_request_host_for_links_subject_or_site(settings, user):
    settings.PUBLIC_BASE_URL = "https://trainer.example"
    settings.ALLOWED_HOSTS = ["testserver"]
    request = RequestFactory().get("/", HTTP_HOST="attacker.example.test")
    request.user = user
    request.support_mail = True
    with context.request_context(request):
        adapter = SupportAccountAdapter()
        reset_url = adapter.get_reset_password_from_key_url("uid-token")
        adapter.send_password_reset_mail(
            user, user.email, {"user": user, "password_reset_url": reset_url}
        )
        EmailAddress.objects.get(user=user).send_confirmation(request)
    assert len(mail.outbox) == 2
    for message in mail.outbox:
        assert "attacker.example.test" not in message.subject + message.body
        assert "[trainer.example]" in message.subject
        assert "Hello from trainer.example!" in message.body
        assert "https://trainer.example/accounts/" in message.body


@pytest.mark.parametrize("dimension", ["key", "ip", "user"])
def test_authentication_counters_are_shared_between_backend_instances(staff, dimension):
    from allauth.core.internal import ratelimit

    workers = [SharedAuthenticationCache("trainer_shared_cache", {}) for _ in range(2)]
    request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.15")
    request.user = staff
    arguments = {
        "request": request,
        "app": "allauth.account",
        "action": "shared_test",
        "key": str(staff.pk),
        "user": staff,
        "config": {"shared_test": f"2/5m/{dimension}"},
    }
    for worker in workers:
        with patch.object(ratelimit, "cache", worker):
            assert ratelimit.consume(**arguments)
    with patch.object(ratelimit, "cache", workers[0]):
        assert not ratelimit.consume(**arguments)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("expired_entry", [False, True])
def test_shared_cache_add_is_atomic_across_independent_connections(expired_entry):
    worker_count = 8
    barrier = Barrier(worker_count)
    key = "concurrent-atomic-add"
    if expired_entry:
        cache.set(key, "old", timeout=-1)

    def consume(index):
        close_old_connections()
        try:
            worker = SharedAuthenticationCache("trainer_shared_cache", {})
            barrier.wait(timeout=10)
            return worker.add(key, index, timeout=60)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(consume, range(worker_count)))
    assert results.count(True) == 1


@pytest.mark.django_db(transaction=True)
def test_shared_allauth_rate_limit_does_not_lose_concurrent_attempts():
    from allauth.core.internal import ratelimit

    worker_count = 8
    barrier = Barrier(worker_count)

    def consume(_):
        close_old_connections()
        try:
            request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.16")
            barrier.wait(timeout=10)
            return bool(
                ratelimit.consume(
                    request,
                    app="allauth.account",
                    action="parallel_test",
                    key="staff-account",
                    config={"parallel_test": "2/5m/key"},
                )
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(consume, range(worker_count)))
    assert results.count(True) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("expired_entry", [False, True])
def test_totp_code_cannot_be_replayed_across_worker_connections(staff, expired_entry):
    secret = generate_totp_secret()
    factor = TOTP.activate(staff, secret).instance
    code = format_hotp_value(hotp_value(secret, int(time.time()) // 30))
    if expired_entry:
        cache.set(TOTP(factor)._get_used_cache_key(code), "old", timeout=-1)
    barrier = Barrier(4)

    def authenticate(_):
        close_old_connections()
        try:
            independent_factor = Authenticator.objects.get(pk=factor.pk)
            barrier.wait(timeout=10)
            return independent_factor.wrap().validate_code(code)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(authenticate, range(4)))
    assert results.count(True) == 1


def test_shared_cache_never_evicts_live_security_markers_at_capacity():
    backend = SharedAuthenticationCache(
        "trainer_shared_cache", {"OPTIONS": {"MAX_ENTRIES": 1, "CULL_FREQUENCY": 0}}
    )
    assert backend.add("live-replay-marker", True, timeout=60)
    for index in range(10):
        backend.set(f"other-counter-{index}", index, timeout=60)
    assert backend.get("live-replay-marker") is True
    assert not backend.add("live-replay-marker", True, timeout=60)


def test_future_mfa_timestamp_never_grants_admin_access(client, staff, factor):
    client.force_login(staff)
    prove(client, staff, factor, age=-300)
    assert urlsplit(client.get("/admin/").url).path == reverse("mfa_reauthenticate")


def test_mfa_proof_older_than_session_lifetime_is_rejected(client, staff, factor, settings):
    client.force_login(staff)
    prove(client, staff, factor, age=settings.SESSION_COOKIE_AGE + 1)
    assert urlsplit(client.get("/admin/").url).path == reverse("mfa_reauthenticate")
