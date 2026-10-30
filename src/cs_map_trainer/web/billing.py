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
from django.db import transaction
from django.utils import timezone

from .models import BillingAccount, BillingEvent, SteamIdentity
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
}


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

    def validate_price(self):
        if not settings.STRIPE_PRICE_ID:
            raise IntakeError("billing_not_configured", 503)
        price = self.call("GET", f"prices/{identifier(settings.STRIPE_PRICE_ID)}")
        if (
            price.get("id") != settings.STRIPE_PRICE_ID
            or price.get("active") is not True
            or price.get("currency") != "usd"
            or price.get("unit_amount") != 799
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


def paid_access(identity):
    return (
        bool(identity.owner_id)
        and BillingAccount.objects.filter(
            owner_id=identity.owner_id,
            closed=False,
            paid_until__gt=timezone.now(),
        ).exists()
    )


def _lock_identity(user):
    try:
        return SteamIdentity.objects.select_for_update().get(owner=user)
    except SteamIdentity.DoesNotExist as error:
        raise IntakeError("verified_steam_required", 403) from error


def _paid_period(stripe, subscription):
    sub_id = identifier(subscription["id"])
    for invoice in stripe.iterate(
        "invoices",
        {"subscription": sub_id, "status": "paid"},
    ):
        if (
            invoice["customer"] != subscription["customer"]
            or invoice["status"] != "paid"
            or invoice["currency"] != "usd"
            or invoice["amount_paid"] < 799
        ):
            continue
        periods = []
        for line in stripe.iterate(f"invoices/{identifier(invoice['id'])}/lines", {}):
            pricing = line.get("pricing") or {}
            price = pricing.get("price_details") or {}
            if price.get("price") == settings.STRIPE_PRICE_ID and line["amount"] >= 799:
                start = datetime.fromtimestamp(line["period"]["start"], UTC)
                end = datetime.fromtimestamp(line["period"]["end"], UTC)
                if start <= timezone.now() and end > start:
                    periods.append(end)
        if periods:
            return max(periods)
    return None


def _sync(account, stripe):
    stripe.validate_price()
    subscriptions = list(
        stripe.iterate(
            "subscriptions",
            {"customer": account.customer_id, "status": "all"},
        )
    )
    candidates = []
    for sub in subscriptions:
        if sub["customer"] != account.customer_id:
            raise ValueError("Stripe customer mismatch")
        items = sub["items"]
        if items["has_more"] or len(items["data"]) != 1:
            raise IntakeError("billing_subscription_mismatch", 503)
        item = items["data"][0]
        if item["price"]["id"] != settings.STRIPE_PRICE_ID or item["quantity"] != 1:
            raise IntakeError("billing_subscription_mismatch", 503)
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
    if candidates:
        until, sub = candidates[0]
        account.paid_until = until
        account.subscription_id = identifier(sub["id"])
        account.status = sub["status"]
        account.cancel_at_period_end = sub["cancel_at_period_end"]
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
def checkout(user):
    identity = _lock_identity(user)
    stripe = Stripe()
    origin = public_origin()
    account, _ = BillingAccount.objects.select_for_update().get_or_create(owner=user)
    if account.closed:
        raise IntakeError("billing_account_closed", 409)
    try:
        if not account.customer_id:
            customer_key = hmac.new(
                settings.SECRET_KEY.encode(),
                f"{identity.pk}:{user.pk}".encode(),
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
                return _hosted_url(previous["url"], "checkout.stripe.com")
            account.checkout_id = ""
            account.checkout_generation += 1
        pending = list(
            stripe.iterate(
                "subscriptions",
                {"customer": account.customer_id, "status": "all"},
            )
        )
        if any(sub["status"] not in {"canceled", "incomplete_expired"} for sub in pending):
            raise IntakeError("subscription_already_exists", 409)
        session = stripe.call(
            "POST",
            "checkout/sessions",
            {
                "mode": "subscription",
                "customer": account.customer_id,
                "line_items[0][price]": settings.STRIPE_PRICE_ID,
                "line_items[0][quantity]": 1,
                "success_url": f"{origin}/account/billing/return/",
                "cancel_url": f"{origin}/account/#billing",
                "payment_method_types[0]": "card",
            },
            key=f"cmt-checkout-{account.customer_id}-{account.checkout_generation}",
        )
        account.checkout_id = identifier(session["id"])
        account.save()
        return _hosted_url(session["url"], "checkout.stripe.com")
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, IntakeError):
            raise
        raise _protocol_error(error) from error


@transaction.atomic
def reconcile_user(user):
    _lock_identity(user)
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
    _lock_identity(user)
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


def _cancel_customer(account, stripe):
    for session in stripe.iterate(
        "checkout/sessions",
        {"customer": account.customer_id, "status": "open"},
    ):
        session_id = identifier(session["id"])
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
            if result["status"] not in {"complete", "expired"}:
                raise ValueError("Checkout still open") from error
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
    SteamIdentity.objects.select_for_update().filter(owner=user).first()
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
        SteamIdentity.objects.select_for_update().filter(owner_id=account.owner_id).first()
    return BillingAccount.objects.select_for_update().get(pk=account_id)


def _reconcile(account, stripe):
    if account.closed or not account.owner_id:
        _cancel_customer(account, stripe)
        account.closed = True
        account.paid_until = None
        account.status = "closed"
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
