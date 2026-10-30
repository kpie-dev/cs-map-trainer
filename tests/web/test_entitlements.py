import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.utils import timezone

from cs_map_trainer.web import billing, entitlements, services
from cs_map_trainer.web.models import AccountPolicy, BillingAccount, Upload
from cs_map_trainer.web.presentation import error_message

pytestmark = pytest.mark.django_db
STEAM = "76561198000000001"


def initiate(user, storage):
    return services.initiate(user, uuid.uuid4(), 32, STEAM, storage)


def finish(upload):
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.READY, cleanup_pending=False)


def test_default_and_nullable_override_follow_global_limit(user, settings):
    settings.DEMO_MONTHLY_LIMIT = 7
    assert entitlements.monthly_limit(user) == 7
    AccountPolicy.objects.create(owner=user)
    assert entitlements.monthly_limit(user) == 7
    settings.DEMO_MONTHLY_LIMIT = 9
    assert entitlements.monthly_limit(user) == 9
    assert not entitlements.manual_access(user)
    assert not entitlements.pro_access(user)


@pytest.mark.parametrize("limit", [0, 1, 5])
def test_override_enforced_and_removal_restores_default(user, storage, settings, limit):
    settings.DEMO_MONTHLY_LIMIT = 8
    policy = AccountPolicy.objects.create(owner=user, monthly_limit_override=limit)
    assert entitlements.monthly_limit(user) == limit
    for _ in range(limit):
        finish(initiate(user, storage))
    with pytest.raises(services.IntakeError, match="monthly_demo_limit") as caught:
        initiate(user, storage)
    assert caught.value.status == 429
    policy.monthly_limit_override = None
    policy.save()
    assert entitlements.monthly_limit(user) == 8
    assert initiate(user, storage)


def test_policy_helpers_use_prefetched_policy(user, django_assert_num_queries):
    policy = AccountPolicy.objects.create(owner=user, monthly_limit_override=4)
    prefetched = get_user_model().objects.select_related("account_policy").get(pk=user.pk)
    with django_assert_num_queries(0):
        assert entitlements.monthly_limit(prefetched) == 4
        assert not entitlements.manual_access(prefetched)
    AccountPolicy.objects.filter(pk=policy.pk).update(
        monthly_limit_override=0, manual_pro_until=timezone.now() + timedelta(days=1)
    )
    fresh = get_user_model().objects.get(pk=user.pk)
    assert entitlements.monthly_limit(fresh) == 0
    assert entitlements.manual_access(fresh)


def test_policy_helpers_use_prefetched_absence(user, django_assert_num_queries, settings):
    prefetched = get_user_model().objects.select_related("account_policy").get(pk=user.pk)
    with django_assert_num_queries(0):
        assert entitlements.monthly_limit(prefetched) == settings.DEMO_MONTHLY_LIMIT
        assert not entitlements.manual_access(prefetched)


def test_intake_uses_fresh_policy_instead_of_cached_policy(user, storage):
    policy = AccountPolicy.objects.create(owner=user, monthly_limit_override=5)
    assert user.account_policy == policy
    AccountPolicy.objects.filter(pk=policy.pk).update(monthly_limit_override=0)
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        initiate(user, storage)
    storage.begin.assert_not_called()


@pytest.mark.parametrize("offset,active", [(-1, False), (0, False), (1, True)])
def test_manual_access_expiry_is_strict(user, offset, active):
    now = timezone.now()
    AccountPolicy.objects.create(owner=user, manual_pro_until=now + timedelta(microseconds=offset))
    with patch("cs_map_trainer.web.entitlements.timezone.now", return_value=now):
        assert entitlements.manual_access(user) is active
        assert entitlements.pro_access(user) is active
    assert not billing.paid_access(user)


@pytest.mark.parametrize("paid,manual", [(True, False), (False, True), (True, True)])
def test_pro_sources_bypass_only_quota(user, storage, paid, manual):
    policy = AccountPolicy.objects.create(
        owner=user,
        monthly_limit_override=0,
        manual_pro_until=timezone.now() + timedelta(days=1) if manual else None,
    )
    account = BillingAccount.objects.create(
        owner=user, paid_until=timezone.now() + timedelta(days=1) if paid else None
    )
    assert billing.paid_access(user) is paid
    assert entitlements.manual_access(user) is manual
    assert entitlements.pro_access(user)
    for _ in range(4):
        finish(initiate(user, storage))
    active = initiate(user, storage)
    with pytest.raises(services.IntakeError, match="active_upload_exists"):
        initiate(user, storage)
    with pytest.raises(services.IntakeError, match="invalid_demo_size"):
        services.initiate(user, uuid.uuid4(), 1024**3 + 1, STEAM, storage)
    finish(active)
    Upload.objects.filter(pk=active.pk).update(cleanup_pending=True)
    with pytest.raises(services.IntakeError, match="input_cleanup_pending"):
        initiate(user, storage)
    Upload.objects.filter(pk=active.pk).update(cleanup_pending=False)
    policy.manual_pro_until = None
    policy.save()
    assert entitlements.pro_access(user) is paid
    account.paid_until = None
    account.save()
    assert not entitlements.pro_access(user)
    assert services.quota_used(user) == 5
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        initiate(user, storage)


def test_revoking_paid_access_keeps_manual_access(user):
    AccountPolicy.objects.create(owner=user, manual_pro_until=timezone.now() + timedelta(days=1))
    account = BillingAccount.objects.create(
        owner=user, paid_until=timezone.now() + timedelta(days=1)
    )
    account.closed = True
    account.save()
    assert not billing.paid_access(user)
    assert entitlements.pro_access(user)


def test_lowered_limit_clamps_ui_remaining_without_removing_history(api, user, storage):
    for _ in range(2):
        finish(initiate(user, storage))
    AccountPolicy.objects.create(owner=user, monthly_limit_override=1)
    response = api.get("/account/")
    assert response.context["quota_used"] == 2
    assert response.context["quota_remaining"] == 0
    assert Upload.objects.filter(owner=user).count() == 2
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        initiate(user, storage)


def test_custom_limit_preserves_utc_month_boundary(user, storage):
    AccountPolicy.objects.create(owner=user, monthly_limit_override=1)
    boundary = datetime(2026, 11, 1, tzinfo=UTC)
    with patch("cs_map_trainer.web.services.timezone.now", return_value=boundary):
        upload = initiate(user, storage)
        finish(upload)
        Upload.objects.filter(pk=upload.pk).update(
            accepted_at=boundary - timedelta(microseconds=1), created_at=boundary
        )
        assert services.quota_used(user) == 0
        Upload.objects.filter(pk=upload.pk).update(accepted_at=boundary)
        assert services.quota_used(user) == 1
        with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
            initiate(user, storage)


def test_manual_expiry_restores_custom_limit_and_retains_usage(user, storage):
    now = timezone.now()
    AccountPolicy.objects.create(
        owner=user, monthly_limit_override=1, manual_pro_until=now + timedelta(hours=1)
    )
    for _ in range(2):
        finish(initiate(user, storage))
    with patch(
        "cs_map_trainer.web.entitlements.timezone.now", return_value=now + timedelta(hours=1)
    ):
        assert not entitlements.manual_access(user)
        assert services.quota_used(user) == 2
        with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
            initiate(user, storage)


def test_initiate_rechecks_active_status_before_idempotent_return(user, upload, storage):
    get_user_model().objects.filter(pk=user.pk).update(is_active=False)
    assert user.is_active
    for request_id in (upload.request_id, uuid.uuid4()):
        with pytest.raises(services.IntakeError, match="account_blocked") as caught:
            services.initiate(user, request_id, 32, STEAM, storage)
        assert caught.value.status == 403
    assert Upload.objects.count() == 1
    storage.begin.assert_called_once()


@pytest.mark.parametrize("state", [Upload.State.UPLOADING, Upload.State.QUEUED, Upload.State.READY])
def test_complete_rechecks_active_status_before_idempotent_return(user, upload, storage, state):
    Upload.objects.filter(pk=upload.pk).update(state=state)
    get_user_model().objects.filter(pk=user.pk).update(is_active=False)
    assert user.is_active
    with patch.object(services, "dispatch") as dispatch:
        with pytest.raises(services.IntakeError, match="account_blocked") as caught:
            services.complete(user, upload.pk, storage)
    assert caught.value.status == 403
    storage.complete.assert_not_called()
    dispatch.assert_not_called()
    upload.refresh_from_db()
    assert upload.state == state
    assert upload.accepted_at is None


def test_complete_locks_account_before_upload(user, upload, storage):
    with patch.object(services, "lock_account", wraps=services.lock_account) as lock:
        storage.complete.side_effect = lambda _: lock.assert_called_once_with(user)
        services.complete(user, upload.pk, storage)
        lock.assert_called_once_with(user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["initiate", "complete"])
def test_blocking_serializes_with_intake(user, upload, storage, operation):
    attempted_lock = Event()
    original_lock = services.lock_account

    def observed_lock(owner):
        attempted_lock.set()
        return original_lock(owner)

    def attempt():
        close_old_connections()
        try:
            with pytest.raises(services.IntakeError, match="account_blocked") as caught:
                if operation == "initiate":
                    services.initiate(user, upload.request_id, 32, STEAM, storage)
                else:
                    services.complete(user, upload.pk, storage)
            return caught.value.status
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            locked = original_lock(user)
            locked.is_active = False
            locked.save(update_fields=["is_active"])
            with patch.object(services, "lock_account", side_effect=observed_lock):
                result = pool.submit(attempt)
                assert attempted_lock.wait(timeout=5)
        assert result.result(timeout=5) == 403
    storage.complete.assert_not_called()
    storage.begin.assert_called_once()


def test_account_and_intake_ui_use_custom_limit(api, user):
    AccountPolicy.objects.create(owner=user, monthly_limit_override=0)
    for path in ("/account/", "/"):
        response = api.get(path)
        text = response.content.decode()
        assert response.context["quota_limit"] == 0
        assert "0/0" in text
        assert "3 analyses per" not in text
        assert "your 0 free analyses" in text
    assert "3 free analyses" not in error_message("monthly_demo_limit")


def test_manual_pro_ui_is_not_presented_as_paid_subscription(api, user):
    AccountPolicy.objects.create(owner=user, manual_pro_until=timezone.now() + timedelta(days=1))
    response = api.get("/account/")
    text = response.content.decode()
    assert response.context["paid_plan"]
    assert response.context["manual_pro"]
    assert not response.context["stripe_paid_plan"]
    assert "PRO / UNLIMITED" in text
    assert "Manual Pro access until" in text
    assert "not a paid Stripe subscription" in text
    assert "Paid access until" not in text
    assert "You are on the Free plan." not in text
    assert "Subscribe to Pro / $4.99/month" in text


def test_both_pro_sources_are_shown_separately(api, user):
    AccountPolicy.objects.create(owner=user, manual_pro_until=timezone.now() + timedelta(days=1))
    BillingAccount.objects.create(owner=user, paid_until=timezone.now() + timedelta(days=2))
    response = api.get("/account/")
    text = response.content.decode()
    assert response.context["stripe_paid_plan"]
    assert "Paid access until" in text
    assert "Manual Pro access until" in text
    assert "Subscribe to Pro / $4.99/month" not in text


def test_public_default_pricing_copy_is_preserved(client):
    assert "3 analyses per account per UTC calendar month" in client.get("/").content.decode()
