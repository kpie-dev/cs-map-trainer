import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client
from django.utils import timezone

from cs_map_trainer.web import billing, services, tasks
from cs_map_trainer.web.models import BillingAccount, BillingEvent, Upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def stripe(settings):
    settings.STRIPE_SECRET_KEY = "test-only-stripe-key"
    settings.STRIPE_WEBHOOK_SECRET = "test-only-webhook-secret"
    settings.STRIPE_PRICE_ID = "price_monthly"
    settings.STRIPE_COACH_PRICE_ID = "price_coach"
    settings.STRIPE_LEGACY_PRO_PRICE_ID = "price_legacy"
    settings.STRIPE_PORTAL_CONFIGURATION_ID = "bpc_monthly"
    settings.PUBLIC_BASE_URL = "https://trainer.example.test"
    now = timezone.now()
    state = SimpleNamespace(
        price={
            "id": "price_monthly",
            "active": True,
            "currency": "usd",
            "unit_amount": 499,
            "type": "recurring",
            "recurring": {"interval": "month", "interval_count": 1, "usage_type": "licensed"},
        },
        subscriptions=[],
        schedules=[],
        created_schedule_keys={},
        invoices=[
            {
                "id": "in_paid",
                "customer": "cus_fixture",
                "status": "paid",
                "currency": "usd",
                "amount_paid": 499,
            }
        ],
        lines=[
            {
                "id": "il_paid",
                "amount": 499,
                "pricing": {"price_details": {"price": "price_monthly"}},
                "period": {"start": int(now.timestamp()) - 100, "end": int(now.timestamp()) + 3600},
            }
        ],
        session={"id": "cs_fixture", "status": "open", "url": "https://checkout.stripe.com/c/pay"},
        open_sessions=[],
        portal={
            "id": "bpc_monthly",
            "active": True,
            "features": {
                "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
                "subscription_update": {"enabled": False},
            },
        },
    )

    def remote(method, url, **kwargs):
        assert url.startswith("https://api.stripe.com/v1/")
        assert kwargs["headers"]["Stripe-Version"] == billing.API_VERSION
        assert kwargs["allow_redirects"] is False
        path = url.removeprefix("https://api.stripe.com/v1/")
        if path == "prices/price_monthly":
            result = state.price
        elif path == "prices/price_coach":
            result = {**state.price, "id": "price_coach", "unit_amount": 1999}
        elif path == "customers":
            result = {"id": "cus_fixture"}
        elif path == "subscriptions":
            result = {"data": state.subscriptions, "has_more": False}
        elif path == "subscription_schedules" and method == "GET":
            result = {"data": state.schedules, "has_more": False}
        elif path == "subscription_schedules" and method == "POST":
            sub = next(
                item
                for item in state.subscriptions
                if item["id"] == kwargs["data"]["from_subscription"]
            )
            item = sub["items"]["data"][0]
            key = kwargs["headers"]["Idempotency-Key"]
            if key in state.created_schedule_keys:
                existing = next(
                    item
                    for item in state.schedules
                    if item["id"] == state.created_schedule_keys[key]
                )
                return Mock(status_code=200, json=Mock(return_value=deepcopy(existing)))
            if sub.get("schedule"):
                return Mock(
                    status_code=400,
                    json=Mock(return_value={"error": {"code": "subscription_schedule_exists"}}),
                )
            result = {
                "id": "sub_sched_fixture",
                "customer": sub["customer"],
                "subscription": sub["id"],
                "status": "active",
                "metadata": {},
                "current_phase": {
                    "start_date": item["current_period_start"],
                    "end_date": item["current_period_end"],
                },
                "phases": [],
            }
            sub["schedule"] = result["id"]
            state.schedules.append(result)
            state.created_schedule_keys[key] = result["id"]
        elif path.startswith("subscription_schedules/"):
            result = next(item for item in state.schedules if item["id"] == path.split("/")[1])
            if path.endswith("/release"):
                result["status"] = "released"
                for sub in state.subscriptions:
                    sub["schedule"] = None
            elif path.endswith("/cancel"):
                result["status"] = "canceled"
                for sub in state.subscriptions:
                    if sub.get("schedule") == result["id"]:
                        sub["status"] = "canceled"
            elif method == "POST":
                data = kwargs["data"]
                result["metadata"] = {"application": data["metadata[application]"]}
                result["phases"] = [
                    {
                        "start_date": data[f"phases[{i}][start_date]"],
                        "items": [
                            {
                                "price": data[f"phases[{i}][items][0][price]"],
                                "quantity": 1,
                            }
                        ],
                    }
                    for i in (0, 1)
                ]
        elif path.startswith("subscriptions/") and method == "DELETE":
            sub = next(item for item in state.subscriptions if item["id"] == path.split("/")[1])
            sub["status"] = "canceled"
            result = sub
        elif path == "invoices":
            result = {"data": state.invoices, "has_more": False}
        elif path == "invoices/in_paid/lines":
            result = {"data": state.lines, "has_more": False}
        elif path == "checkout/sessions" and method == "POST":
            result = state.session
        elif path == "checkout/sessions":
            result = {"data": state.open_sessions, "has_more": False}
        elif path.endswith("/expire"):
            result = {"id": "cs_fixture", "status": "expired"}
        elif path == "checkout/sessions/cs_fixture":
            result = state.session
        elif path == "billing_portal/configurations/bpc_monthly":
            result = state.portal
        elif path == "billing_portal/sessions":
            result = {"url": "https://billing.stripe.com/p/session/fixture"}
        else:
            raise AssertionError(f"Unexpected Stripe request {method} {path}")
        return Mock(status_code=200, json=Mock(return_value=deepcopy(result)))

    with patch("cs_map_trainer.web.billing.requests.request", side_effect=remote) as request:
        state.request = request
        yield state


@pytest.fixture
def account(user):
    return BillingAccount.objects.create(owner=user, customer_id="cus_fixture")


def subscription(status="active", price="price_monthly"):
    now = int(timezone.now().timestamp())
    return {
        "id": "sub_fixture",
        "customer": "cus_fixture",
        "status": status,
        "created": 100,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_fixture",
                    "price": {"id": price},
                    "quantity": 1,
                    "current_period_start": now - 120,
                    "current_period_end": now + 3600,
                }
            ],
            "has_more": False,
        },
    }


def event(event_id="evt_fixture", kind="invoice.paid"):
    return {
        "id": event_id,
        "type": kind,
        "data": {"object": {"customer": "cus_fixture", "status": "active"}},
    }


def deliver(client, settings, payload, *, timestamp=None, secret=None, suffix=""):
    raw = json.dumps(payload).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(
        (secret or settings.STRIPE_WEBHOOK_SECRET).encode(),
        str(timestamp).encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        "/billing/stripe/webhook/",
        raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={digest}{suffix}",
    )


def test_checkout_uses_fixed_price_and_reuses_open_session(api, stripe, user):
    url = "/account/billing/checkout/"
    response = api.post(url, {"price": "price_injected", "amount": 1})
    assert response.status_code == 302
    assert response.url == "https://checkout.stripe.com/c/pay"
    account = BillingAccount.objects.get(owner=user)
    assert account.checkout_id == "cs_fixture"
    assert account.paid_until is None
    assert not billing.paid_access(user)
    posts = [
        item
        for item in stripe.request.call_args_list
        if item.args[0] == "POST" and item.args[1].endswith("/checkout/sessions")
    ]
    assert len(posts) == 1
    assert posts[0].kwargs["data"]["line_items[0][price]"] == "price_monthly"
    assert posts[0].kwargs["data"]["line_items[0][quantity]"] == 1
    assert posts[0].kwargs["data"]["mode"] == "subscription"
    assert "Idempotency-Key" in posts[0].kwargs["headers"]
    assert all(
        "76561198000000001" not in call.kwargs["headers"].get("Idempotency-Key", "")
        for call in stripe.request.call_args_list
    )
    assert api.post(url).url == response.url
    assert (
        sum(
            item.args[0] == "POST" and item.args[1].endswith("/checkout/sessions")
            for item in stripe.request.call_args_list
        )
        == 1
    )


def test_return_does_not_grant_paid_access(api, account):
    response = api.get("/account/billing/return/?session_id=cs_untrusted")
    assert response.status_code == 302
    account.refresh_from_db()
    assert account.paid_until is None
    assert not billing.paid_access(account.owner)


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "pln"),
        ("unit_amount", 798),
        ("active", False),
        ("type", "one_time"),
    ],
)
def test_checkout_rejects_misconfigured_price(api, stripe, field, value):
    stripe.price[field] = value
    response = api.post("/account/billing/checkout/")
    assert response.status_code == 503
    assert b"billing_price_mismatch" in response.content


def test_checkout_rejects_nonmonthly_price(api, stripe):
    stripe.price["recurring"]["interval"] = "year"
    assert api.post("/account/billing/checkout/").status_code == 503


def test_expired_checkout_advances_stable_idempotency_generation(api, account, stripe):
    account.checkout_id = "cs_fixture"
    account.save()
    stripe.session["status"] = "expired"
    assert api.post("/account/billing/checkout/").status_code == 302
    account.refresh_from_db()
    assert account.checkout_generation == 1
    calls = [
        call
        for call in stripe.request.call_args_list
        if call.args[0] == "POST" and call.args[1].endswith("/checkout/sessions")
    ]
    assert calls[0].kwargs["headers"]["Idempotency-Key"].endswith("-1")


def test_duplicate_subscription_is_not_created(api, account, stripe):
    stripe.subscriptions = [subscription("incomplete")]
    response = api.post("/account/billing/checkout/")
    assert response.status_code == 409
    assert b"subscription_already_exists" in response.content


def test_checkout_recovers_paid_access_from_stripe_without_duplicate_charge(api, account, stripe):
    stripe.subscriptions = [subscription()]
    assert api.post("/account/billing/checkout/").url == "https://trainer.example.test/account/"
    account.refresh_from_db()
    assert account.paid_until > timezone.now()


def test_verified_webhook_grants_only_invoice_proven_period(client, account, stripe, settings):
    stripe.subscriptions = [subscription()]
    assert deliver(client, settings, event()).status_code == 200
    account.refresh_from_db()
    expected = datetime.fromtimestamp(stripe.lines[0]["period"]["end"], UTC)
    assert account.paid_until == expected
    assert billing.paid_access(account.owner)
    assert BillingEvent.objects.count() == 1
    stripe.request.reset_mock()
    assert deliver(client, settings, event()).status_code == 200
    stripe.request.assert_not_called()
    assert BillingEvent.objects.count() == 1


@pytest.mark.parametrize(
    "invoice_change,line_change",
    [
        ({"amount_paid": 0}, {}),
        ({"status": "open"}, {}),
        ({"currency": "pln"}, {}),
        ({"customer": "cus_other"}, {}),
        ({}, {"amount": 0}),
        ({}, {"pricing": {"price_details": {"price": "price_other"}}}),
    ],
)
def test_unpaid_or_wrong_price_never_grants_access(
    client,
    account,
    stripe,
    settings,
    invoice_change,
    line_change,
):
    stripe.subscriptions = [subscription()]
    stripe.invoices[0].update(invoice_change)
    stripe.lines[0].update(line_change)
    assert deliver(client, settings, event()).status_code == 200
    account.refresh_from_db()
    assert account.paid_until is None


def test_failed_renewal_keeps_only_already_paid_time(client, account, stripe, settings):
    stripe.subscriptions = [subscription("past_due")]
    deliver(client, settings, event(kind="invoice.payment_failed"))
    assert billing.paid_access(account.owner)
    stripe.lines[0]["period"]["end"] = int(time.time()) - 1
    stripe.lines[0]["period"]["start"] = int(time.time()) - 3600
    deliver(client, settings, event("evt_later", "invoice.payment_failed"))
    assert not billing.paid_access(account.owner)


def test_cancel_at_period_end_keeps_access_until_paid_end(client, account, stripe, settings):
    stripe.subscriptions = [subscription()]
    stripe.subscriptions[0]["cancel_at_period_end"] = True
    deliver(client, settings, event(kind="customer.subscription.updated"))
    account.refresh_from_db()
    assert account.cancel_at_period_end
    assert billing.paid_access(account.owner)
    with patch("cs_map_trainer.web.billing.timezone.now", return_value=account.paid_until):
        assert not billing.paid_access(account.owner)


def test_stale_paid_event_cannot_resurrect_canceled_subscription(
    client,
    account,
    stripe,
    settings,
):
    stripe.subscriptions = [subscription("canceled")]
    account.paid_until = timezone.now() + timedelta(days=3)
    account.save()
    assert deliver(client, settings, event()).status_code == 200
    account.refresh_from_db()
    assert account.paid_until is None


@pytest.mark.parametrize("kind", ["trialing", "incomplete", "incomplete_expired", "paused"])
def test_nonpaid_statuses_do_not_grant_access(client, account, stripe, settings, kind):
    stripe.subscriptions = [subscription(kind)]
    deliver(client, settings, event())
    assert not billing.paid_access(account.owner)


@pytest.mark.parametrize("offset,secret", [(-301, None), (301, None), (0, "wrong-secret")])
def test_invalid_or_expired_signatures_are_rejected(
    client,
    account,
    stripe,
    settings,
    offset,
    secret,
):
    response = deliver(
        client,
        settings,
        event(),
        timestamp=int(time.time()) + offset,
        secret=secret,
    )
    assert response.status_code == 400
    stripe.request.assert_not_called()
    assert not BillingEvent.objects.exists()


def test_signature_body_tampering_and_missing_header_are_rejected(client, stripe):
    assert (
        client.post(
            "/billing/stripe/webhook/",
            "{}",
            content_type="application/json",
        ).status_code
        == 400
    )
    assert client.get("/billing/stripe/webhook/").status_code == 405
    assert (
        client.post(
            "/billing/stripe/webhook/",
            b"x" * (1024 * 1024 + 1),
            content_type="application/json",
        ).status_code
        == 413
    )
    stripe.request.assert_not_called()


def test_signed_webhook_is_csrf_exempt_but_purchase_is_not(user, account, stripe, settings):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    for path in ["checkout", "portal", "refresh"]:
        assert client.post(f"/account/billing/{path}/").status_code == 403
    assert deliver(client, settings, event()).status_code == 200


def test_unknown_customer_or_event_is_not_mapped_by_metadata(client, stripe, settings):
    payload = event()
    payload["data"]["object"]["metadata"] = {"user": "1"}
    assert deliver(client, settings, payload).status_code == 200
    assert deliver(client, settings, event(kind="unhandled.event")).status_code == 200
    assert not BillingAccount.objects.exists()
    stripe.request.assert_not_called()


def test_failed_webhook_can_retry_without_false_processed_receipt(
    client,
    account,
    stripe,
    settings,
):
    handler = stripe.request.side_effect
    stripe.request.side_effect = requests.Timeout()
    assert deliver(client, settings, event()).status_code == 503
    assert not BillingEvent.objects.exists()
    stripe.request.side_effect = handler
    assert deliver(client, settings, event()).status_code == 200
    assert BillingEvent.objects.count() == 1


def test_portal_enforces_cancel_at_period_end_and_no_plan_changes(api, account, stripe):
    response = api.post("/account/billing/portal/")
    assert response.status_code == 302
    assert response.url.startswith("https://billing.stripe.com/")
    stripe.portal["features"]["subscription_cancel"]["mode"] = "immediately"
    assert api.post("/account/billing/portal/").status_code == 503
    stripe.portal["features"]["subscription_cancel"]["mode"] = "at_period_end"
    stripe.portal["features"]["subscription_update"]["enabled"] = True
    assert api.post("/account/billing/portal/").status_code == 503


def test_other_account_cannot_choose_customer_or_subscription(api, account, stripe):
    api.post("/account/billing/portal/", {"customer": "cus_other", "subscription": "sub_other"})
    calls = [
        call
        for call in stripe.request.call_args_list
        if call.args[0] == "POST" and call.args[1].endswith("/billing_portal/sessions")
    ]
    assert calls[0].kwargs["data"]["customer"] == account.customer_id


def test_missing_configuration_is_explicit(api, settings):
    settings.STRIPE_SECRET_KEY = ""
    response = api.post("/account/billing/checkout/")
    assert response.status_code == 503
    assert b"billing_not_configured" in response.content


def test_checkout_requires_verified_email_without_steam(api, user, stripe):
    EmailAddress.objects.filter(user=user).update(verified=False)
    assert api.post("/account/billing/checkout/").url == "/accounts/email/"
    EmailAddress.objects.filter(user=user).update(verified=True)
    stripe.request.assert_not_called()
    assert api.post("/account/billing/checkout/").status_code == 302


def test_account_delete_cancels_remote_then_preserves_only_closed_billing_reference(
    api,
    account,
    stripe,
):
    stripe.subscriptions = [subscription()]
    stripe.open_sessions = [{"id": "cs_fixture"}]
    owner = account.owner
    response = api.post(
        "/account/delete/",
        {"confirm": "yes", "password": "some-password"},
    )
    assert response.status_code == 302
    assert not get_user_model().objects.filter(pk=owner.pk).exists()
    account.refresh_from_db()
    assert account.owner is None
    assert account.closed
    assert account.paid_until is None
    assert stripe.subscriptions[0]["status"] == "canceled"
    calls = stripe.request.call_args_list
    assert any(call.args[1].endswith("/cs_fixture/expire") for call in calls)
    deletion = next(call for call in calls if call.args[0] == "DELETE")
    assert deletion.kwargs["data"] == {"invoice_now": "false", "prorate": "false"}


def test_stripe_failure_prevents_account_deletion(api, account, stripe):
    stripe.request.side_effect = requests.Timeout()
    response = api.post(
        "/account/delete/",
        {"confirm": "yes", "password": "some-password"},
    )
    assert response.status_code == 503
    assert get_user_model().objects.filter(pk=account.owner_id).exists()
    account.refresh_from_db()
    assert not account.closed


def test_direct_user_delete_also_cancels_stripe(account, stripe):
    stripe.subscriptions = [subscription()]
    account.owner.delete()
    account.refresh_from_db()
    assert account.closed and account.owner is None
    assert stripe.subscriptions[0]["status"] == "canceled"


def test_deletion_can_cancel_existing_customer_without_price_configuration(
    api,
    account,
    stripe,
    settings,
):
    stripe.subscriptions = [subscription()]
    settings.STRIPE_PRICE_ID = ""
    response = api.post(
        "/account/delete/",
        {"confirm": "yes", "password": "some-password"},
    )
    assert response.status_code == 302
    assert stripe.subscriptions[0]["status"] == "canceled"


def test_late_events_after_deletion_cancel_instead_of_granting(
    client,
    account,
    stripe,
    settings,
):
    account.closed = True
    account.owner = None
    account.save()
    stripe.subscriptions = [subscription()]
    assert deliver(client, settings, event()).status_code == 200
    account.refresh_from_db()
    assert account.paid_until is None
    assert stripe.subscriptions[0]["status"] == "canceled"


def test_month_boundary_is_utc_and_inclusive(user, storage):
    now = datetime(2026, 11, 1, tzinfo=UTC)
    with patch("cs_map_trainer.web.services.timezone.now", return_value=now):
        item = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
        assert services.quota_used(user) == 1
        Upload.objects.filter(pk=item.pk).update(
            state="ready",
            cleanup_pending=False,
            created_at=now - timedelta(microseconds=1),
        )
        assert services.quota_used(user) == 0
        Upload.objects.filter(pk=item.pk).update(created_at=now)
        assert services.quota_used(user) == 1


def test_paid_plan_has_no_count_limit_but_keeps_size_and_active_limit(user, storage, account):
    account.paid_until = timezone.now() + timedelta(days=1)
    account.save()
    for _ in range(12):
        upload = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
        Upload.objects.filter(pk=upload.pk).update(state="ready", cleanup_pending=False)
    active = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
    with pytest.raises(services.IntakeError, match="active_upload_exists"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
    with pytest.raises(services.IntakeError, match="invalid_demo_size"):
        services.initiate(user, uuid.uuid4(), 1024**3 + 1, "76561198000000001", storage)
    account.paid_until = timezone.now()
    account.save()
    Upload.objects.filter(pk=active.pk).update(state="ready", cleanup_pending=False)
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)


def test_closed_or_foreign_account_cannot_grant_entitlement(user, account):
    account.paid_until = timezone.now() + timedelta(days=1)
    account.closed = True
    account.save()
    assert not billing.paid_access(user)
    account.closed = False
    account.owner = get_user_model().objects.create_user("other", "other@example.test")
    account.save()
    assert not billing.paid_access(user)


def test_account_ui_shows_paid_plan_without_network_on_get(api, account, stripe):
    account.paid_until = timezone.now() + timedelta(days=1)
    account.save()
    response = api.get("/account/")
    assert "Pro is active" in response.content.decode()
    assert "$4.99/month" in response.content.decode()
    assert "UNLIMITED" in response.content.decode()
    assert "7 DAYS" not in response.content.decode()
    stripe.request.assert_not_called()


def test_monthly_tombstone_keeps_same_month_usage_after_eight_days(
    user,
    storage,
    settings,
    tmp_path,
):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    with patch("cs_map_trainer.web.services.timezone.now", return_value=now):
        upload = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
    Upload.objects.filter(pk=upload.pk).update(
        created_at=now - timedelta(days=8),
        state="ready",
        cleanup_pending=False,
    )
    services.delete_account(user)
    settings.WORK_ROOT = tmp_path
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(
            tasks.timezone,
            "now",
            return_value=now,
        ),
    ):
        tasks.maintain()
    assert Upload.objects.filter(pk=upload.pk).exists()
    assert upload.player_steam_id == "76561198000000001"


def test_reconciliation_command_recovers_delayed_webhook(account, stripe):
    stripe.subscriptions = [subscription()]
    call_command("reconcile_subscriptions", stdout=StringIO())
    account.refresh_from_db()
    assert account.paid_until > timezone.now()


def test_reconciliation_cancels_orphaned_subscriptions_after_account_deletion(account, stripe):
    account.owner = None
    account.closed = True
    account.save()
    stripe.subscriptions = [subscription()]
    call_command("reconcile_subscriptions", stdout=StringIO())
    assert stripe.subscriptions[0]["status"] == "canceled"


def test_checkout_transport_retry_uses_the_same_remote_idempotency_keys(api, stripe):
    handler = stripe.request.side_effect
    failed = False

    def lose_checkout_response(method, url, **kwargs):
        nonlocal failed
        response = handler(method, url, **kwargs)
        if method == "POST" and url.endswith("/checkout/sessions") and not failed:
            failed = True
            raise requests.Timeout()
        return response

    stripe.request.side_effect = lose_checkout_response
    assert api.post("/account/billing/checkout/").status_code == 503
    assert api.post("/account/billing/checkout/").status_code == 302
    for path in ["/checkout/sessions", "/customers"]:
        calls = [
            call
            for call in stripe.request.call_args_list
            if call.args[0] == "POST" and call.args[1].endswith(path)
        ]
        assert len(calls) == 2
        assert (
            calls[0].kwargs["headers"]["Idempotency-Key"]
            == (calls[1].kwargs["headers"]["Idempotency-Key"])
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_does_not_create_two_sessions(user, stripe):
    def start():
        close_old_connections()
        try:
            return billing.checkout(get_user_model().objects.get(pk=user.pk))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert len(set(results)) == 1
    assert (
        sum(
            call.args[0] == "POST" and call.args[1].endswith("/checkout/sessions")
            for call in stripe.request.call_args_list
        )
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_webhooks_are_serialized(account, stripe):
    stripe.subscriptions = [subscription()]

    def receive():
        close_old_connections()
        try:
            billing.process_event(event())
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: receive(), range(2)))
    assert BillingEvent.objects.count() == 1
    assert (
        sum(
            call.args[1].endswith("/prices/price_monthly") for call in stripe.request.call_args_list
        )
        == 1
    )


def test_new_account_has_independent_quota_for_same_player(user, storage):
    for _ in range(3):
        upload = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
        Upload.objects.filter(pk=upload.pk).update(state="ready", cleanup_pending=False)
    services.delete_account(user)
    Upload.objects.filter(owner=None).update(cleanup_pending=False)
    other = get_user_model().objects.create_user("new-account", "new@example.test")
    assert services.initiate(other, uuid.uuid4(), 32, "76561198000000001", storage)


def test_external_hosted_url_is_rejected(api, stripe):
    stripe.session["url"] = "https://evil.example/checkout"
    response = api.post("/account/billing/checkout/")
    assert response.status_code == 503
    assert b"billing_invalid_response" in response.content


def test_unconfirmed_remote_cancellation_does_not_delete_user(api, account, stripe):
    stripe.subscriptions = [subscription()]
    handler = stripe.request.side_effect

    def unconfirmed(method, url, **kwargs):
        if method == "DELETE":
            return Mock(status_code=200, json=Mock(return_value=subscription()))
        return handler(method, url, **kwargs)

    stripe.request.side_effect = unconfirmed
    assert (
        api.post(
            "/account/delete/",
            {"confirm": "yes", "password": "some-password"},
        ).status_code
        == 503
    )
    assert get_user_model().objects.filter(pk=account.owner_id).exists()


def test_api_error_does_not_leak_stripe_response(api, stripe):
    stripe.request.side_effect = None
    stripe.request.return_value = Mock(
        status_code=500,
        json=Mock(return_value={"error": {"message": "sensitive-provider-detail"}}),
    )
    response = api.post("/account/billing/checkout/")
    assert response.status_code == 503
    assert b"sensitive-provider-detail" not in response.content


def test_stripe_pagination_does_not_truncate_customers_invoices(stripe):
    client = billing.Stripe()
    with patch.object(
        client,
        "call",
        side_effect=[
            {"data": [{"id": "in_first"}], "has_more": True},
            {"data": [{"id": "in_last"}], "has_more": False},
        ],
    ) as call:
        assert len(list(client.iterate("invoices", {"subscription": "sub_fixture"}))) == 2
        assert call.call_args.args[2]["starting_after"] == "in_first"
