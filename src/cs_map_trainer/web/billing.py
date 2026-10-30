"""Stripe-hosted payments and server-side, paid-through entitlements."""

import hashlib
import hmac
import json
import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .identity import lock_account
from .models import BillingAccount, BillingEvent
from .services import IntakeError

logger = logging.getLogger(__name__)
API_VERSION = "2025-06-30.basil"
WEBHOOK_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "invoice.voided",
    "invoice.marked_uncollectible",
    "subscription_schedule.created",
    "subscription_schedule.updated",
    "subscription_schedule.released",
    "subscription_schedule.canceled",
    "subscription_schedule.completed",
    "subscription_schedule.aborted",
    "subscription_schedule.expiring",
}


def catalog():
    """Only these server-configured prices can buy an entitlement."""
    prices = [
        (settings.STRIPE_PRICE_ID, "pro", 499),
        (settings.STRIPE_COACH_PRICE_ID, "coach", 1999),
        (settings.STRIPE_LEGACY_PRO_PRICE_ID, "pro", 799),
    ]
    configured = [(price, plan, amount) for price, plan, amount in prices if price]
    if len({price for price, _, _ in configured}) != len(configured):
        raise IntakeError("billing_price_mismatch", 503)
    return {price: (plan, amount) for price, plan, amount in configured}


def plan_price(plan):
    if not isinstance(plan, str) or plan not in {"pro", "coach"}:
        raise IntakeError("invalid_billing_plan", 400)
    price = settings.STRIPE_PRICE_ID if plan == "pro" else settings.STRIPE_COACH_PRICE_ID
    if not price:
        raise IntakeError("billing_not_configured", 503)
    catalog()
    return identifier(price)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,128}", value):
        raise ValueError("Invalid Stripe identifier")
    return value


class StripeFailure(IntakeError):
    def __init__(self, remote_code=""):
        self.remote_code = remote_code
        super().__init__("billing_unavailable", 503)


class Stripe:
    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise IntakeError("billing_not_configured", 503)

    def call(self, method, path, data=None, *, key=None):
        headers = {"Stripe-Version": API_VERSION}
        if key:
            headers["Idempotency-Key"] = key
        try:
            response = requests.request(
                method,
                f"https://api.stripe.com/v1/{path}",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers=headers,
                params=data if method == "GET" else None,
                data=data if method != "GET" else None,
                timeout=(5, 25),
                allow_redirects=False,
            )
        except requests.RequestException as error:
            logger.warning("Stripe transport failure (%s)", type(error).__name__)
            raise StripeFailure() from error
        try:
            result = response.json()
        except ValueError as error:
            logger.error("Stripe returned non-JSON response (HTTP %s)", response.status_code)
            raise StripeFailure() from error
        if not isinstance(result, dict):
            raise StripeFailure()
        if response.status_code < 200 or response.status_code >= 300:
            logger.warning("Stripe request failed (HTTP %s)", response.status_code)
            remote_error = result.get("error")
            code = remote_error.get("code", "") if isinstance(remote_error, dict) else ""
            raise StripeFailure(code)
        return result

    def iterate(self, path, data):
        params = {**data, "limit": 100}
        while True:
            result = self.call("GET", path, params)
            items = result["data"]
            if not isinstance(items, list) or type(result["has_more"]) is not bool:
                raise ValueError("Invalid Stripe pagination")
            yield from items
            if not result["has_more"]:
                break
            if not items:
                raise ValueError("Empty Stripe pagination")
            cursor = identifier(items[-1]["id"])
            if cursor == params.get("starting_after"):
                raise ValueError("Repeated Stripe pagination")
            params["starting_after"] = cursor

    def validate_price(self, plan="pro"):
        price_id = plan_price(plan)
        price = self.call("GET", f"prices/{price_id}")
        if (
            price.get("id") != price_id
            or price.get("active") is not True
            or price.get("currency") != "usd"
            or price.get("unit_amount") != catalog()[price_id][1]
            or price.get("type") != "recurring"
            or price.get("recurring", {}).get("interval") != "month"
            or price["recurring"].get("interval_count") != 1
            or price["recurring"].get("usage_type") != "licensed"
        ):
            raise IntakeError("billing_price_mismatch", 503)


def public_origin():
    origin = settings.PUBLIC_BASE_URL.rstrip("/")
    parts = urlsplit(origin)
    if (
        parts.scheme not in ({"http", "https"} if settings.DEBUG else {"https"})
        or not parts.netloc
        or parts.username
        or parts.password
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise IntakeError("billing_not_configured", 503)
    return origin


def paid_access(user):
    return (
        bool(user.pk)
        and BillingAccount.objects.filter(
            owner_id=user.pk,
            closed=False,
            plan__in=("pro", "coach"),
            paid_until__gt=timezone.now(),
        ).exists()
    )


def coach_access(user):
    return (
        bool(user.pk)
        and BillingAccount.objects.filter(
            owner_id=user.pk, closed=False, plan="coach", paid_until__gt=timezone.now()
        ).exists()
    )


def _subscription_item(subscription):
    items = subscription["items"]
    if items["has_more"] or len(items["data"]) != 1:
        raise IntakeError("billing_subscription_mismatch", 503)
    item = items["data"][0]
    if item["price"]["id"] not in catalog() or item["quantity"] != 1:
        raise IntakeError("billing_subscription_mismatch", 503)
    return item


def _paid_period(stripe, subscription):
    sub_id = identifier(subscription["id"])
    item = _subscription_item(subscription)
    price_id = item["price"]["id"]
    _, amount = catalog()[price_id]
    periods = []
    now = timezone.now()
    for invoice in stripe.iterate(
        "invoices",
        {"subscription": sub_id, "status": "paid"},
    ):
        if (
            invoice["customer"] != subscription["customer"]
            or invoice["status"] != "paid"
            or invoice["currency"] != "usd"
            or invoice["amount_paid"] < amount
        ):
            continue
        for line in stripe.iterate(f"invoices/{identifier(invoice['id'])}/lines", {}):
            pricing = line.get("pricing") or {}
            price = pricing.get("price_details") or {}
            details = (line.get("parent") or {}).get("subscription_item_details") or {}
            if details.get("proration") or line.get("proration"):
                continue
            if details.get("subscription", sub_id) != sub_id:
                continue
            if item.get("id") and details.get("subscription_item", item["id"]) != item["id"]:
                continue
            if price.get("price") == price_id and line["amount"] >= amount:
                start = datetime.fromtimestamp(line["period"]["start"], UTC)
                end = datetime.fromtimestamp(line["period"]["end"], UTC)
                current_start = item.get("current_period_start")
                current_end = item.get("current_period_end")
                if current_start is not None and start.timestamp() < current_start:
                    continue
                if current_end is not None and end.timestamp() > current_end:
                    continue
                if start <= now < end:
                    periods.append((start, end))
    return max(periods)[1] if periods else None


def _schedule_object(stripe, subscription):
    value = subscription.get("schedule")
    if not value:
        return None
    schedule_id = identifier(value["id"] if isinstance(value, dict) else value)
    schedule = stripe.call("GET", f"subscription_schedules/{schedule_id}")
    if (
        schedule["id"] != schedule_id
        or schedule["customer"] != subscription["customer"]
        or schedule.get("subscription") != subscription["id"]
    ):
        raise ValueError("Subscription schedule mismatch")
    return schedule


def _sync_schedule(account, stripe, subscription):
    if subscription["status"] in {"canceled", "incomplete_expired"}:
        return
    schedule = _schedule_object(stripe, subscription)
    if not schedule or schedule["status"] not in {"active", "not_started"}:
        return
    if subscription["cancel_at_period_end"] or subscription.get("cancel_at"):
        # Releasing must preserve the portal's cancellation date, not revive renewal.
        released = stripe.call(
            "POST",
            f"subscription_schedules/{identifier(schedule['id'])}/release",
            {"preserve_cancel_date": "true"},
        )
        if released["status"] != "released":
            raise ValueError("Schedule release not confirmed")
        return
    account.schedule_id = identifier(schedule["id"])
    now = timezone.now().timestamp()
    current_price = _subscription_item(subscription)["price"]["id"]
    for phase in schedule["phases"]:
        if phase["start_date"] <= now:
            continue
        items = phase["items"]
        if len(items) != 1 or items[0]["quantity"] != 1:
            continue
        price = items[0]["price"]
        price_id = price["id"] if isinstance(price, dict) else price
        if price_id in catalog() and price_id != current_price:
            account.scheduled_plan = catalog()[price_id][0]
            account.scheduled_at = datetime.fromtimestamp(phase["start_date"], UTC)
            break


def _schedule_subscription(account, stripe, subscription, plan):
    item = _subscription_item(subscription)
    target_price = plan_price(plan)
    stripe.validate_price(plan)
    boundary = item["current_period_end"]
    start = item["current_period_start"]
    if boundary <= timezone.now().timestamp() or start >= boundary:
        raise IntakeError("billing_period_mismatch", 409)
    schedule = _schedule_object(stripe, subscription)
    creation_key = f"cmt-schedule-{subscription['id']}-{boundary}"
    if schedule:
        if schedule["status"] != "active":
            raise IntakeError("billing_schedule_exists", 409)
        metadata = schedule.get("metadata") or {}
        if metadata and metadata.get("application") != "cs-map-trainer":
            raise IntakeError("billing_schedule_exists", 409)
        if not metadata:
            # A response can be lost between adopting the subscription and
            # setting its phases. Only a replay of our creation key proves
            # ownership; never overwrite an unrelated operator schedule.
            try:
                recovered = stripe.call(
                    "POST",
                    "subscription_schedules",
                    {"from_subscription": subscription["id"]},
                    key=creation_key,
                )
            except StripeFailure as error:
                if error.remote_code:
                    raise IntakeError("billing_schedule_exists", 409) from error
                raise
            if recovered["id"] != schedule["id"]:
                raise IntakeError("billing_schedule_exists", 409)
    elif item["price"]["id"] == target_price:
        return
    else:
        schedule = stripe.call(
            "POST",
            "subscription_schedules",
            {"from_subscription": subscription["id"]},
            key=creation_key,
        )
    schedule_id = identifier(schedule["id"])
    current_phase = schedule["current_phase"]
    if current_phase["end_date"] != boundary:
        raise IntakeError("billing_period_mismatch", 409)
    data = {
        "end_behavior": "release",
        "proration_behavior": "none",
        "metadata[application]": "cs-map-trainer",
        "phases[0][start_date]": current_phase["start_date"],
        "phases[0][end_date]": boundary,
        "phases[0][items][0][price]": item["price"]["id"],
        "phases[0][items][0][quantity]": 1,
        "phases[0][proration_behavior]": "none",
        "phases[1][start_date]": boundary,
        "phases[1][items][0][price]": target_price,
        "phases[1][items][0][quantity]": 1,
        "phases[1][iterations]": 1,
        "phases[1][proration_behavior]": "none",
    }
    # Replacing the complete future phase is naturally idempotent. Do not reuse
    # an old idempotency key when the user changes their mind more than once.
    result = stripe.call("POST", f"subscription_schedules/{schedule_id}", data)
    if result["id"] != schedule_id or result["status"] != "active":
        raise ValueError("Schedule update not confirmed")
    account.schedule_id = schedule_id
    account.scheduled_plan = plan if target_price != item["price"]["id"] else ""
    account.scheduled_at = datetime.fromtimestamp(boundary, UTC) if account.scheduled_plan else None
    account.save()


@transaction.atomic
def schedule_plan(user, plan):
    plan_price(plan)
    lock_account(user)
    account = BillingAccount.objects.select_for_update().filter(owner=user, closed=False).first()
    if not account or not account.customer_id:
        raise IntakeError("billing_customer_required", 409)
    stripe = Stripe()
    try:
        _sync(account, stripe)
        if not account.paid_until or account.paid_until <= timezone.now():
            raise IntakeError("billing_paid_subscription_required", 409)
        subscriptions = list(
            stripe.iterate("subscriptions", {"customer": account.customer_id, "status": "all"})
        )
        live = [
            sub for sub in subscriptions if sub["status"] not in {"canceled", "incomplete_expired"}
        ]
        if (
            len(live) != 1
            or live[0]["id"] != account.subscription_id
            or live[0]["customer"] != account.customer_id
            or live[0]["status"] != "active"
            or live[0]["cancel_at_period_end"]
            or live[0].get("cancel_at")
        ):
            raise IntakeError("billing_subscription_change_unavailable", 409)
        _schedule_subscription(account, stripe, live[0], plan)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


@transaction.atomic
def migrate_legacy_price(account_id, *, dry_run=True):
    """Schedule a legacy renewal or recover its setup, without changing its price now."""
    account = _lock_account(account_id)
    if account.closed or not account.owner_id or not account.customer_id:
        return "skipped"
    stripe = Stripe()
    try:
        subscriptions = list(
            stripe.iterate("subscriptions", {"customer": account.customer_id, "status": "all"})
        )
        live = [
            sub for sub in subscriptions if sub["status"] not in {"canceled", "incomplete_expired"}
        ]
        if len(live) != 1:
            return "skipped"
        sub = live[0]
        if sub["customer"] != account.customer_id:
            raise ValueError("Stripe customer mismatch")
        item = _subscription_item(sub)
        if (
            sub["status"] != "active"
            or item["price"]["id"] != settings.STRIPE_LEGACY_PRO_PRICE_ID
            or sub["cancel_at_period_end"]
            or sub.get("cancel_at")
            or account.scheduled_plan
            or not _paid_period(stripe, sub)
        ):
            return "skipped"
        boundary = item["current_period_end"]
        if boundary <= timezone.now().timestamp():
            return "skipped"
        schedule = _schedule_object(stripe, sub)
        if schedule:
            metadata = schedule.get("metadata") or {}
            if (
                schedule["status"] != "active"
                or (metadata and metadata.get("application") != "cs-map-trainer")
                or any(
                    phase["start_date"] > timezone.now().timestamp() for phase in schedule["phases"]
                )
            ):
                return "skipped"
        stripe.validate_price("pro")
        if dry_run:
            return "would schedule"
        _schedule_subscription(account, stripe, sub, "pro")
        return "scheduled"
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


def _sync(account, stripe):
    stripe.validate_price()
    subscriptions = list(
        stripe.iterate(
            "subscriptions",
            {"customer": account.customer_id, "status": "all"},
        )
    )
    candidates = []
    validated = {"pro"}
    for sub in subscriptions:
        if sub["customer"] != account.customer_id:
            raise ValueError("Stripe customer mismatch")
        if sub["status"] in {"canceled", "incomplete_expired"}:
            candidates.append((None, sub))
            continue
        item = _subscription_item(sub)
        plan = catalog()[item["price"]["id"]][0]
        if plan not in validated:
            stripe.validate_price(plan)
            validated.add(plan)
        paid_until = None
        if sub["status"] in {"active", "past_due", "unpaid"}:
            paid_until = _paid_period(stripe, sub)
        candidates.append((paid_until, sub))
    candidates.sort(
        key=lambda item: (
            item[0] or datetime.min.replace(tzinfo=UTC),
            item[1]["created"],
            item[1]["id"],
        ),
        reverse=True,
    )
    account.paid_until = None
    account.subscription_id = ""
    account.status = ""
    account.cancel_at_period_end = False
    account.plan = "pro"
    account.schedule_id = ""
    account.scheduled_plan = ""
    account.scheduled_at = None
    if candidates:
        until, sub = candidates[0]
        account.paid_until = until
        account.subscription_id = identifier(sub["id"])
        account.status = sub["status"]
        account.cancel_at_period_end = sub["cancel_at_period_end"]
        if sub["status"] not in {"canceled", "incomplete_expired"}:
            account.plan = catalog()[sub["items"]["data"][0]["price"]["id"]][0]
            _sync_schedule(account, stripe, sub)
    account.synced_at = timezone.now()
    account.save()


def _protocol_error(error):
    logger.error("Invalid Stripe response (%s)", type(error).__name__)
    return IntakeError("billing_invalid_response", 503)


def _hosted_url(value, hostname):
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.hostname != hostname or parts.username or parts.password:
        raise ValueError("Invalid Stripe hosted URL")
    return value


@transaction.atomic
def checkout(user, plan="pro"):
    price_id = plan_price(plan)
    lock_account(user)
    stripe = Stripe()
    origin = public_origin()
    account, _ = BillingAccount.objects.select_for_update().get_or_create(owner=user)
    if account.closed:
        raise IntakeError("billing_account_closed", 409)
    try:
        if plan != "pro":
            stripe.validate_price(plan)
        if not account.customer_id:
            customer_key = hmac.new(
                settings.SECRET_KEY.encode(),
                f"account:{user.pk}".encode(),
                hashlib.sha256,
            ).hexdigest()
            customer = stripe.call(
                "POST",
                "customers",
                {"metadata[application]": "cs-map-trainer"},
                key=f"cmt-customer-{customer_key}",
            )
            account.customer_id = identifier(customer["id"])
            account.save()
        _sync(account, stripe)
        if account.paid_until and account.paid_until > timezone.now():
            return f"{origin}/account/"
        if account.checkout_id:
            previous = stripe.call("GET", f"checkout/sessions/{identifier(account.checkout_id)}")
            if previous["status"] == "open":
                if account.checkout_plan == plan:
                    return _hosted_url(previous["url"], "checkout.stripe.com")
                _expire_checkout(stripe, account.checkout_id)
            account.checkout_id = ""
            account.checkout_plan = ""
            account.checkout_generation += 1
        pending = list(
            stripe.iterate(
                "subscriptions",
                {"customer": account.customer_id, "status": "all"},
            )
        )
        if any(sub["status"] not in {"canceled", "incomplete_expired"} for sub in pending):
            raise IntakeError("subscription_already_exists", 409)
        # A previous response may have been lost before its session ID was saved.
        # Neutralize unknown open sessions before allowing a different plan.
        for previous in stripe.iterate(
            "checkout/sessions", {"customer": account.customer_id, "status": "open"}
        ):
            metadata = previous.get("metadata") or {}
            if metadata.get("application") == "cs-map-trainer" and metadata.get("plan") == plan:
                account.checkout_id = identifier(previous["id"])
                account.checkout_plan = plan
                account.save()
                return _hosted_url(previous["url"], "checkout.stripe.com")
            _expire_checkout(stripe, previous["id"])
            account.checkout_generation += 1
        session = stripe.call(
            "POST",
            "checkout/sessions",
            {
                "mode": "subscription",
                "customer": account.customer_id,
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": 1,
                "success_url": f"{origin}/account/billing/return/",
                "cancel_url": f"{origin}/account/#billing",
                "payment_method_types[0]": "card",
                "metadata[application]": "cs-map-trainer",
                "metadata[plan]": plan,
            },
            key=f"cmt-checkout-{account.customer_id}-{plan}-{account.checkout_generation}",
        )
        account.checkout_id = identifier(session["id"])
        account.checkout_plan = plan
        account.save()
        return _hosted_url(session["url"], "checkout.stripe.com")
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


@transaction.atomic
def reconcile_user(user):
    lock_account(user)
    account = BillingAccount.objects.select_for_update().filter(owner=user, closed=False).first()
    if account and account.customer_id:
        try:
            _sync(account, Stripe())
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            if isinstance(error, IntakeError):
                raise
            raise _protocol_error(error) from error


@transaction.atomic
def portal(user):
    lock_account(user)
    account = BillingAccount.objects.select_for_update().filter(owner=user, closed=False).first()
    if not account or not account.customer_id:
        raise IntakeError("billing_customer_required", 409)
    if not settings.STRIPE_PORTAL_CONFIGURATION_ID:
        raise IntakeError("billing_not_configured", 503)
    stripe = Stripe()
    try:
        config = stripe.call(
            "GET",
            f"billing_portal/configurations/{identifier(settings.STRIPE_PORTAL_CONFIGURATION_ID)}",
        )
        features = config["features"]
        if (
            config["active"] is not True
            or features["subscription_cancel"]["enabled"] is not True
            or features["subscription_cancel"]["mode"] != "at_period_end"
            or features["subscription_update"]["enabled"] is not False
        ):
            raise IntakeError("billing_portal_mismatch", 503)
        session = stripe.call(
            "POST",
            "billing_portal/sessions",
            {
                "customer": account.customer_id,
                "configuration": config["id"],
                "return_url": f"{public_origin()}/account/",
            },
        )
        return _hosted_url(session["url"], "billing.stripe.com")
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


def _expire_checkout(stripe, session_id):
    session_id = identifier(session_id)
    try:
        result = stripe.call(
            "POST",
            f"checkout/sessions/{session_id}/expire",
            key=f"cmt-expire-{session_id}",
        )
        if result["id"] != session_id or result["status"] != "expired":
            raise ValueError("Checkout expiration not confirmed")
    except StripeFailure as error:
        if error.remote_code != "checkout_session_not_open":
            raise
        result = stripe.call("GET", f"checkout/sessions/{session_id}")
        if result["status"] != "expired":
            # A completed purchase must be reconciled before another is allowed.
            raise IntakeError("subscription_already_exists", 409) from error


def _cancel_customer(account, stripe):
    for session in stripe.iterate(
        "checkout/sessions",
        {"customer": account.customer_id, "status": "open"},
    ):
        try:
            _expire_checkout(stripe, session["id"])
        except IntakeError as error:
            if error.code != "subscription_already_exists":
                raise
    for schedule in stripe.iterate("subscription_schedules", {"customer": account.customer_id}):
        if schedule["status"] in {"active", "not_started"}:
            result = stripe.call(
                "POST",
                f"subscription_schedules/{identifier(schedule['id'])}/cancel",
                {"invoice_now": "false", "prorate": "false"},
            )
            if result["id"] != schedule["id"] or result["status"] != "canceled":
                raise ValueError("Schedule cancellation not confirmed")
    for subscription in stripe.iterate(
        "subscriptions",
        {"customer": account.customer_id, "status": "all"},
    ):
        if subscription["status"] not in {"canceled", "incomplete_expired"}:
            result = stripe.call(
                "DELETE",
                f"subscriptions/{identifier(subscription['id'])}",
                {"invoice_now": "false", "prorate": "false"},
            )
            if result["id"] != subscription["id"] or result["status"] != "canceled":
                raise ValueError("Subscription cancellation not confirmed")


@transaction.atomic
def close_account(user):
    lock_account(user)
    account = BillingAccount.objects.select_for_update().filter(owner=user).first()
    if not account or account.closed:
        return
    if account.customer_id:
        try:
            _cancel_customer(account, Stripe())
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, IntakeError):
                raise
            raise _protocol_error(error) from error
    account.closed = True
    account.paid_until = None
    account.status = "closed"
    account.schedule_id = ""
    account.scheduled_plan = ""
    account.scheduled_at = None
    account.save()


def verify_signature(raw, signature):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise IntakeError("billing_not_configured", 503)
    try:
        components = [part.split("=", 1) for part in signature.split(",")]
        timestamps = [value for key, value in components if key == "t"]
        if len(timestamps) != 1:
            raise ValueError("Invalid timestamp")
        timestamp = int(timestamps[0])
        if abs(time.time() - timestamp) > 300:
            raise ValueError("Expired signature")
        signed = timestamps[0].encode("ascii") + b"." + raw
        digest = hmac.new(
            settings.STRIPE_WEBHOOK_SECRET.encode(),
            signed,
            hashlib.sha256,
        ).hexdigest()
        if not any(hmac.compare_digest(digest, value) for key, value in components if key == "v1"):
            raise ValueError("Invalid signature")
        event = json.loads(raw)
        identifier(event["id"])
        if not isinstance(event["type"], str):
            raise ValueError("Invalid event")
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        logger.warning("Rejected invalid Stripe webhook signature or envelope")
        raise IntakeError("invalid_billing_webhook", 400) from error
    return event


def _lock_account(account_id):
    account = BillingAccount.objects.get(pk=account_id)
    if account.owner_id:
        get_user_model().objects.select_for_update().filter(pk=account.owner_id).first()
    return BillingAccount.objects.select_for_update().get(pk=account_id)


def _reconcile(account, stripe):
    if account.closed or not account.owner_id:
        _cancel_customer(account, stripe)
        account.closed = True
        account.paid_until = None
        account.status = "closed"
        account.schedule_id = ""
        account.scheduled_plan = ""
        account.scheduled_at = None
        account.synced_at = timezone.now()
        account.save()
    else:
        _sync(account, stripe)


@transaction.atomic
def reconcile_account(account_id):
    account = _lock_account(account_id)
    if not account.customer_id:
        return
    try:
        _reconcile(account, Stripe())
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


@transaction.atomic
def process_event(event):
    if event["type"] not in WEBHOOK_EVENTS:
        return
    try:
        customer_id = identifier(event["data"]["object"]["customer"])
        account = BillingAccount.objects.filter(customer_id=customer_id).first()
        if account is None:
            logger.warning("Stripe webhook customer not linked locally")
            return
        account = _lock_account(account.pk)
        if BillingEvent.objects.filter(event_id=event["id"]).exists():
            return
        stripe = Stripe()
        _reconcile(account, stripe)
        BillingEvent.objects.create(event_id=event["id"], account=account)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error
