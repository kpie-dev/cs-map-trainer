import smtplib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cs_map_trainer.web import billing, services, support
from cs_map_trainer.web.adapters import SupportAccountAdapter
from cs_map_trainer.web.models import AccountPolicy, BillingAccount, SupportAudit, Upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(settings):
    settings.PUBLIC_BASE_URL = "https://trainer.example.test"
    cache.clear()
    call_command("configure_support_roles", verbosity=0)
    actor = get_user_model().objects.create_user(
        "operator", "operator@example.test", "some-password", is_staff=True
    )
    actor.groups.add(Group.objects.get(name="Account Operators"))
    EmailAddress.objects.create(user=actor, email=actor.email, primary=True, verified=True)
    return actor


def action_request(actor):
    request = RequestFactory().post("/admin/", HTTP_HOST="testserver")
    request.user = actor
    request.session = {}
    return request


@pytest.fixture
def support_client(operator):
    client = Client()
    client.force_login(operator)
    authenticator = Authenticator.objects.create(
        user=operator, type=Authenticator.Type.TOTP, data={}
    )
    session = client.session
    session["account_authentication_methods_user"] = str(operator.pk)
    session["account_authentication_methods"] = [
        {"method": "password", "at": time.time()},
        {"method": "mfa", "at": time.time(), "id": authenticator.pk, "type": "totp"},
    ]
    session.save()
    return client


def run_action(operator, user, action, **kwargs):
    support.execute_action(
        action_request(operator), user, action, {"reason": "Support ticket", **kwargs}
    )


def test_roles_are_minimal_and_idempotent(operator):
    call_command("configure_support_roles", verbosity=0)
    assert set(
        Group.objects.get(name="Support").permissions.values_list("codename", flat=True)
    ) == {"support_view", "support_email"}
    assert Group.objects.get(name="Account Operators").user_set.count() == 1
    assert not operator.has_perm("auth.change_user")


def test_role_assignment_and_removal_are_explicit(user):
    call_command("configure_support_roles", email=user.email, role="Support", verbosity=0)
    user.refresh_from_db()
    assert user.is_staff
    assert user.groups.get().name == "Support"
    call_command("configure_support_roles", email=user.email, remove=True, verbosity=0)
    user.refresh_from_db()
    assert not user.is_staff
    assert not user.groups.exists()


@pytest.mark.parametrize("role", ["Support", "Account Operators", None])
def test_role_changes_remove_managed_direct_permissions(operator, user, role):
    direct = Permission.objects.filter(
        content_type__app_label="trainer",
        content_type__model="accountpolicy",
        codename__startswith="support_",
    )
    unrelated = Permission.objects.get(content_type__app_label="auth", codename="view_user")
    operator.user_permissions.add(*direct, unrelated)
    options = {"role": role} if role else {"remove": True}
    call_command("configure_support_roles", email=operator.email, verbosity=0, **options)
    actor = get_user_model().objects.get(pk=operator.pk)
    assert set(actor.user_permissions.values_list("pk", flat=True)) == {unrelated.pk}
    assert support.can_operate(actor, user, "block") == (role == "Account Operators")
    assert actor.has_perm("trainer.support_billing") == (role == "Account Operators")
    assert actor.is_staff == (role is not None)
    assert actor.has_perm("trainer.support_view") == (role is not None)


@pytest.mark.parametrize("remove", [False, True])
def test_conflicting_external_group_prevents_role_change(operator, remove):
    group = Group.objects.create(name="Custom elevated support")
    group.permissions.add(
        Permission.objects.get(content_type__app_label="trainer", codename="support_manage")
    )
    operator.groups.add(group)
    before_groups = set(operator.groups.values_list("pk", flat=True))
    options = {"remove": True} if remove else {"role": "Support"}
    with pytest.raises(CommandError, match="Another group grants"):
        call_command("configure_support_roles", email=operator.email, verbosity=0, **options)
    operator.refresh_from_db()
    assert set(operator.groups.values_list("pk", flat=True)) == before_groups
    assert operator.is_staff


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("flow", ["reset", "change"])
def test_password_save_cannot_undo_interleaved_account_block(client, operator, user, flow):
    from allauth.account.forms import default_token_generator
    from allauth.account.utils import user_pk_to_url_str

    password = "a-new-unique-password-9843"
    if flow == "reset":
        response = client.get(
            reverse(
                "account_reset_password_from_key",
                kwargs={
                    "uidb36": user_pk_to_url_str(user),
                    "key": default_token_generator.make_token(user),
                },
            )
        )
        assert response.status_code == 302
        url = response.url
        data = {"password1": password, "password2": password}
    else:
        client.force_login(user)
        url = reverse("account_change_password")
        data = {"oldpassword": "some-password", "password1": password, "password2": password}
    save_password = SupportAccountAdapter.set_password

    def block_then_save(adapter, stale_user, new_password):
        assert stale_user.is_active
        run_action(operator, user, "block")
        save_password(adapter, stale_user, new_password)

    with patch.object(SupportAccountAdapter, "set_password", block_then_save):
        response = client.post(url, data)
    assert response.status_code == 302
    user.refresh_from_db()
    assert not user.is_active
    assert user.check_password(password)
    assert AccountPolicy.objects.get(owner=user).session_version == 1
    assert SupportAudit.objects.get(action="block").outcome == "success"
    assert client.get("/backend/history/").status_code == 403
    fresh_client = Client()
    fresh_client.post(reverse("account_login"), {"login": user.email, "password": password})
    assert SESSION_KEY not in fresh_client.session


def test_limit_and_manual_pro_do_not_modify_billing_or_usage(operator, user):
    account = BillingAccount.objects.create(
        owner=user, paid_until=timezone.now() + timedelta(days=2)
    )
    run_action(operator, user, "limit", monthly_limit=0)
    until = timezone.now() + timedelta(days=10)
    run_action(operator, user, "grant_pro", pro_until=until)
    policy = AccountPolicy.objects.get(owner=user)
    assert policy.monthly_limit_override == 0
    assert policy.manual_pro_until == until
    run_action(operator, user, "revoke_pro")
    run_action(operator, user, "limit", monthly_limit=None)
    policy.refresh_from_db()
    account.refresh_from_db()
    assert policy.monthly_limit_override is None
    assert policy.manual_pro_until is None
    assert billing.paid_access(user)
    assert SupportAudit.objects.filter(outcome="success").count() == 4
    assert account.paid_until is not None
    assert Upload.objects.count() == 0


def test_block_retains_data_and_paid_subscription(operator, user, upload):
    account = BillingAccount.objects.create(
        owner=user, status="active", paid_until=timezone.now() + timedelta(days=2)
    )
    run_action(operator, user, "block")
    user.refresh_from_db()
    account.refresh_from_db()
    upload.refresh_from_db()
    assert not user.is_active
    assert account.status == "active"
    assert upload.state == Upload.State.UPLOADING
    assert AccountPolicy.objects.get(owner=user).session_version == 1
    run_action(operator, user, "unblock")
    user.refresh_from_db()
    assert user.is_active
    assert AccountPolicy.objects.get(owner=user).session_version == 1


@pytest.mark.parametrize("target_staff", [True, False])
def test_no_self_or_staff_operations(operator, user, target_staff):
    target = user if target_staff else operator
    if target_staff:
        target.is_staff = True
        target.save()
    with pytest.raises(PermissionDenied):
        run_action(operator, target, "block")
    assert not SupportAudit.objects.exists()


def test_support_cannot_change_policy(operator, user):
    operator.groups.set([Group.objects.get(name="Support")])
    with pytest.raises(PermissionDenied):
        run_action(operator, user, "limit", monthly_limit=20)


def test_invalid_or_expired_pro_is_not_saved(operator, user):
    with pytest.raises(services.IntakeError, match="support_invalid_expiry"):
        run_action(operator, user, "grant_pro", pro_until=timezone.now() - timedelta(seconds=1))
    assert AccountPolicy.objects.get(owner=user).manual_pro_until is None
    assert SupportAudit.objects.get().outcome == "failed"


def test_reset_uses_primary_verified_email_and_trusted_origin(operator, user):
    request = action_request(operator)
    request.META["HTTP_HOST"] = "attacker.example.test"
    support.execute_action(request, user, "reset_password", {"reason": "Customer request"})
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    assert "https://trainer.example.test/accounts/password/reset/key/" in mail.outbox[0].body
    assert "attacker.example.test" not in mail.outbox[0].body
    audit = SupportAudit.objects.get()
    assert audit.outcome == "success"
    assert "key" not in str(audit.after)
    user.refresh_from_db()
    assert user.check_password("some-password")
    with pytest.raises(services.IntakeError, match="support_email_rate_limited"):
        run_action(operator, user, "reset_password")
    assert len(mail.outbox) == 1


def test_confirmation_does_not_verify_address(operator, user):
    EmailAddress.objects.filter(user=user).update(verified=False)
    run_action(operator, user, "verify_email")
    assert len(mail.outbox) == 1
    assert "https://trainer.example.test/accounts/confirm-email/" in mail.outbox[0].body
    assert not EmailAddress.objects.get(user=user).verified


@pytest.mark.parametrize("action,verified", [("reset_password", False), ("verify_email", True)])
def test_wrong_email_state_is_explicit_error(operator, user, action, verified):
    EmailAddress.objects.filter(user=user).update(verified=verified)
    with pytest.raises(services.IntakeError, match="support_email_state_mismatch"):
        run_action(operator, user, action)
    assert not mail.outbox
    assert SupportAudit.objects.get().outcome == "failed"


def test_smtp_failure_is_audited_not_success(operator, user):
    with patch.object(
        EmailAddress, "send_confirmation", side_effect=smtplib.SMTPException("failed")
    ):
        EmailAddress.objects.filter(user=user).update(verified=False)
        with pytest.raises(services.IntakeError, match="support_email_unavailable"):
            run_action(operator, user, "verify_email")
    assert SupportAudit.objects.get().error_code == "support_email_unavailable"
    assert not mail.outbox


def test_refresh_failure_does_not_change_snapshot(operator, user):
    account = BillingAccount.objects.create(owner=user, customer_id="cus_test", status="active")
    with patch.object(
        billing, "reconcile_user", side_effect=services.IntakeError("billing_unavailable", 503)
    ):
        with pytest.raises(services.IntakeError, match="billing_unavailable"):
            run_action(operator, user, "refresh_billing")
    account.refresh_from_db()
    assert account.status == "active"
    audit = SupportAudit.objects.get()
    assert audit.before == audit.after
    assert audit.outcome == "failed"


def test_card_and_search_share_steam_without_linking_accounts(support_client, user, storage):
    second = get_user_model().objects.create_user("other", "other@example.test", "some-password")
    steam = "76561198000000001"
    for owner in [user, second]:
        upload = services.initiate(owner, uuid.uuid4(), 32, steam, storage)
        Upload.objects.filter(pk=upload.pk).update(state="failed", cleanup_pending=False)
    response = support_client.get(reverse("admin:auth_user_changelist"), {"q": steam})
    assert response.status_code == 200
    assert response.context["cl"].result_count == 2
    with patch.object(billing.Stripe, "call") as stripe:
        response = support_client.get(reverse("admin:auth_user_change", args=[user.pk]))
    assert response.status_code == 200
    assert b"unverified player identifiers" in response.content
    assert b"local snapshot" in response.content
    stripe.assert_not_called()
    assert b"multipart-id" not in response.content


def test_list_query_count_does_not_grow_per_user(support_client, user):
    url = reverse("admin:auth_user_changelist")
    with CaptureQueriesContext(connection) as baseline:
        assert support_client.get(url).status_code == 200
    for index in range(10):
        extra = get_user_model().objects.create_user(
            f"extra{index}", f"extra{index}@example.test", "some-password"
        )
        AccountPolicy.objects.create(owner=extra, monthly_limit_override=index)
    with CaptureQueriesContext(connection) as expanded:
        response = support_client.get(url)
        assert response.status_code == 200
        assert response.context["cl"].result_count == 12
    assert len(expanded) == len(baseline)


def test_action_form_csrf_and_no_standard_edit(support_client, user):
    url = reverse("admin:support_action", args=[user.pk, "limit"])
    response = support_client.get(url)
    assert response.status_code == 200
    assert response.context["form"].fields["reason"].required
    assert AccountPolicy.objects.count() == 0
    response = support_client.post(
        url,
        {
            "reason": "Customer request",
            "monthly_limit": "10",
            "confirm": "on",
        },
    )
    assert response.status_code == 302
    assert AccountPolicy.objects.get(owner=user).monthly_limit_override == 10
    assert support_client.post(reverse("admin:auth_user_change", args=[user.pk])).status_code == 405
    assert support_client.get(reverse("admin:auth_user_delete", args=[user.pk])).status_code == 403
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.cookies = support_client.cookies
    assert csrf_client.post(url, {"reason": "No token", "confirm": "on"}).status_code == 403


def test_support_role_has_only_email_actions(support_client, operator, user):
    operator.groups.set([Group.objects.get(name="Support")])
    response = support_client.get(reverse("admin:auth_user_change", args=[user.pk]))
    assert response.status_code == 200
    assert b"Send password reset link" in response.content
    assert b"Set monthly limit" not in response.content
    assert b"Grant temporary Pro" not in response.content
    assert (
        support_client.get(reverse("admin:support_action", args=[user.pk, "limit"])).status_code
        == 403
    )
    assert (
        support_client.post(
            reverse("admin:support_action", args=[user.pk, "block"]),
            {"reason": "Not permitted", "confirm": "on"},
        ).status_code
        == 403
    )
    assert not SupportAudit.objects.exists()


@pytest.mark.parametrize("value", ["-1", "abc", "2147483648"])
def test_invalid_limit_is_rejected(support_client, user, value):
    response = support_client.post(
        reverse("admin:support_action", args=[user.pk, "limit"]),
        {"reason": "Customer request", "monthly_limit": value, "confirm": "on"},
    )
    assert response.status_code == 200
    assert response.context["form"].errors
    assert not AccountPolicy.objects.filter(owner=user).exists()


def test_audit_cannot_be_modified(support_client, operator, user):
    run_action(operator, user, "limit", monthly_limit=8)
    entry = SupportAudit.objects.get()
    opts = ["admin:trainer_supportaudit_change", "admin:trainer_supportaudit_delete"]
    assert support_client.get(reverse(opts[0], args=[entry.pk])).status_code == 200
    assert (
        support_client.post(reverse(opts[0], args=[entry.pk]), {"reason": "Changed"}).status_code
        == 403
    )
    assert (
        support_client.post(reverse(opts[1], args=[entry.pk]), {"post": "yes"}).status_code == 403
    )
    entry.refresh_from_db()
    assert entry.reason == "Support ticket"


@pytest.mark.django_db(transaction=True)
def test_concurrent_email_actions_send_once(operator, user):
    def send(_):
        close_old_connections()
        try:
            actor = get_user_model().objects.get(pk=operator.pk)
            target = get_user_model().objects.get(pk=user.pk)
            try:
                run_action(actor, target, "reset_password")
                return "sent"
            except services.IntakeError as error:
                return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert sorted(results) == ["sent", "support_email_rate_limited"]
    assert SupportAudit.objects.filter(outcome="success").count() == 1
