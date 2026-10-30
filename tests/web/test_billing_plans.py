import time
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
import requests
import test_billing as fixtures
from django.core.management import call_command
from django.utils import timezone

from cs_map_trainer.web import billing, entitlements
from cs_map_trainer.web.models import AccountPolicy, BillingAccount
from cs_map_trainer.web.services import IntakeError

pytestmark = pytest.mark.django_db
stripe = fixtures.stripe
account = fixtures.account
deliver = fixtures.deliver
event = fixtures.event
subscription = fixtures.subscription


def use_price(stripe, price, amount):
    stripe.subscriptions = [subscription(price=price)]
    stripe.lines[0]["pricing"]["price_details"]["price"] = price
    stripe.lines[0]["amount"] = amount
    stripe.invoices[0]["amount_paid"] = amount


def posts(stripe):
    return [call for call in stripe.request.call_args_list if call.args[0] == "POST"]


def test_coach_checkout_uses_only_server_price(user, stripe):
    billing.checkout(user, "coach")
    purchase = next(call for call in posts(stripe) if call.args[1].endswith("/checkout/sessions"))
    assert purchase.kwargs["data"]["line_items[0][price]"] == "price_coach"
    assert BillingAccount.objects.get(owner=user).checkout_plan == "coach"
    assert not entitlements.coach_access(user)


def test_missing_coach_configuration_does_not_break_pro(user, account, stripe, settings):
    settings.STRIPE_COACH_PRICE_ID = ""
    stripe.subscriptions = [subscription()]
    billing.reconcile_user(user)
    assert billing.paid_access(user)
    with pytest.raises(IntakeError, match="billing_not_configured"):
        billing.schedule_plan(user, "coach")


@pytest.mark.parametrize("plan", ["free", "price_coach", "", None, 1999])
def test_unknown_plan_is_rejected_without_network(user, stripe, plan):
    with pytest.raises(IntakeError, match="invalid_billing_plan"):
        billing.checkout(user, plan)
    stripe.request.assert_not_called()


def test_different_checkout_plan_expires_previous_before_new_purchase(user, stripe):
    billing.checkout(user)
    stripe.request.reset_mock()
    billing.checkout(user, "coach")
    changes = posts(stripe)
    expire = next(i for i, call in enumerate(changes) if call.args[1].endswith("/expire"))
    purchase = next(
        i for i, call in enumerate(changes) if call.args[1].endswith("/checkout/sessions")
    )
    assert expire < purchase
    account = BillingAccount.objects.get(owner=user)
    assert account.checkout_generation == 1
    assert account.checkout_plan == "coach"


def test_lost_checkout_response_can_recover_matching_remote_session(user, account, stripe):
    stripe.open_sessions = [
        {
            **stripe.session,
            "metadata": {"application": "cs-map-trainer", "plan": "coach"},
        }
    ]
    assert billing.checkout(user, "coach") == stripe.session["url"]
    assert not posts(stripe)
    account.refresh_from_db()
    assert account.checkout_plan == "coach"


def test_manual_pro_and_staff_never_grant_coach(user):
    AccountPolicy.objects.update_or_create(
        owner=user, defaults={"manual_pro_until": timezone.now() + timedelta(days=1)}
    )
    user.is_staff = True
    assert entitlements.pro_access(user)
    assert not entitlements.coach_access(user)


def test_paid_coach_inherits_pro_and_legacy_is_only_pro(user, account, stripe):
    use_price(stripe, "price_coach", 1999)
    billing.reconcile_user(user)
    account.refresh_from_db()
    assert account.plan == "coach"
    assert entitlements.coach_access(user)
    assert entitlements.pro_access(user)
    use_price(stripe, "price_legacy", 799)
    billing.reconcile_user(user)
    assert entitlements.pro_access(user)
    assert not entitlements.coach_access(user)


def test_old_coach_invoice_cannot_grant_new_pro_or_unpaid_upgrade(user, account, stripe):
    use_price(stripe, "price_coach", 1999)
    billing.reconcile_user(user)
    assert billing.coach_access(user)
    stripe.subscriptions[0] = subscription()
    billing.reconcile_user(user)
    assert not billing.coach_access(user)
    assert not billing.paid_access(user)
    use_price(stripe, "price_monthly", 499)
    stripe.subscriptions[0] = subscription(price="price_coach")
    billing.reconcile_user(user)
    assert not billing.coach_access(user)


def test_old_same_price_paid_period_does_not_cover_unpaid_coach_renewal(user, account, stripe):
    use_price(stripe, "price_coach", 1999)
    stripe.lines[0]["period"]["start"] -= 3600
    billing.reconcile_user(user)
    assert not billing.coach_access(user)


def test_future_or_prorated_coach_line_does_not_grant(user, account, stripe):
    use_price(stripe, "price_coach", 1999)
    stripe.lines[0]["period"]["start"] = int(time.time()) + 10
    billing.reconcile_user(user)
    assert not billing.coach_access(user)
    stripe.lines[0]["period"]["start"] = int(time.time()) - 100
    stripe.lines[0]["parent"] = {
        "subscription_item_details": {"subscription": "sub_fixture", "proration": True}
    }
    billing.reconcile_user(user)
    assert not billing.coach_access(user)


def test_paid_period_search_is_not_invoice_order_dependent(user, account, stripe):
    stripe.subscriptions = [subscription()]
    older = deepcopy(stripe.lines[0])
    older["period"]["end"] -= 10
    with patch.object(billing.Stripe, "iterate") as iterate:

        def rows(path, data):
            return iter(
                {
                    "subscriptions": stripe.subscriptions,
                    "invoices": [stripe.invoices[0], {**stripe.invoices[0], "id": "in_older"}],
                    "invoices/in_paid/lines": stripe.lines,
                    "invoices/in_older/lines": [older],
                }[path]
            )

        iterate.side_effect = rows
        billing.reconcile_user(user)
    account.refresh_from_db()
    assert int(account.paid_until.timestamp()) == stripe.lines[0]["period"]["end"]


def test_schedule_changes_at_boundary_without_grant_or_proration(user, account, stripe):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    account.refresh_from_db()
    assert account.plan == "pro"
    assert not billing.coach_access(user)
    assert account.scheduled_plan == "coach"
    boundary = stripe.subscriptions[0]["items"]["data"][0]["current_period_end"]
    assert int(account.scheduled_at.timestamp()) == boundary
    update = next(call for call in posts(stripe) if call.args[1].endswith("/sub_sched_fixture"))
    data = update.kwargs["data"]
    assert data["phases[1][start_date]"] == boundary
    assert data["phases[0][end_date]"] == boundary
    assert data["phases[0][items][0][price]"] == "price_monthly"
    assert data["phases[1][items][0][price]"] == "price_coach"
    assert data["proration_behavior"] == data["phases[1][proration_behavior]"] == "none"
    assert not any("/subscriptions/" in call.args[1] for call in posts(stripe))
    billing.schedule_plan(user, "pro")
    account.refresh_from_db()
    assert not account.scheduled_plan
    assert len(stripe.schedules) == 1
    billing.schedule_plan(user, "coach")
    assert len(stripe.schedules) == 1


def test_schedule_creation_response_loss_recovers_without_second_schedule(user, account, stripe):
    stripe.subscriptions = [subscription()]
    handler = stripe.request.side_effect
    fail = True

    def lose_response(method, url, **kwargs):
        nonlocal fail
        response = handler(method, url, **kwargs)
        if method == "POST" and url.endswith("/subscription_schedules") and fail:
            fail = False
            raise requests.Timeout()
        return response

    stripe.request.side_effect = lose_response
    with pytest.raises(billing.StripeFailure):
        billing.schedule_plan(user, "coach")
    assert len(stripe.schedules) == 1
    billing.schedule_plan(user, "coach")
    assert len(stripe.schedules) == 1
    account.refresh_from_db()
    assert account.scheduled_plan == "coach"
    assert not billing.coach_access(user)


def test_unmanaged_schedule_cannot_be_overwritten(user, account, stripe):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    stripe.schedules[0]["metadata"] = {"application": "operator"}
    stripe.created_schedule_keys.clear()
    previous = deepcopy(stripe.schedules[0])
    with pytest.raises(IntakeError, match="billing_schedule_exists"):
        billing.schedule_plan(user, "pro")
    assert stripe.schedules[0] == previous


def test_failed_coach_renewal_never_grants_schedule(user, account, stripe):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    use_price(stripe, "price_monthly", 499)
    stripe.subscriptions[0] = subscription("past_due", price="price_coach")
    billing.reconcile_user(user)
    assert not entitlements.coach_access(user)


@pytest.mark.parametrize("status", ["canceled", "past_due", "unpaid", "incomplete"])
def test_change_requires_active_paid_subscription(user, account, stripe, status):
    stripe.subscriptions = [subscription(status)]
    with pytest.raises(IntakeError):
        billing.schedule_plan(user, "coach")
    assert not stripe.schedules


def test_canceling_subscription_releases_pending_schedule_without_resurrection(
    user, account, stripe, client, settings
):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    stripe.subscriptions[0]["cancel_at_period_end"] = True
    stripe.request.reset_mock()
    assert deliver(client, settings, event(kind="customer.subscription.updated")).status_code == 200
    account.refresh_from_db()
    assert not account.schedule_id
    assert not account.scheduled_plan
    assert stripe.schedules[0]["status"] == "released"
    release = next(call for call in posts(stripe) if call.args[1].endswith("/release"))
    assert release.kwargs["data"] == {"preserve_cancel_date": "true"}
    assert not any("/subscriptions/" in call.args[1] for call in posts(stripe))


def test_account_deletion_cancels_attached_and_future_schedules(user, account, stripe):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    stripe.schedules.append(
        {
            "id": "sub_sched_future",
            "status": "not_started",
            "customer": account.customer_id,
        }
    )
    billing.close_account(user)
    account.refresh_from_db()
    assert account.closed
    assert account.paid_until is None
    assert not account.schedule_id
    assert all(schedule["status"] == "canceled" for schedule in stripe.schedules)
    assert stripe.subscriptions[0]["status"] == "canceled"


def test_schedule_webhook_fetches_current_state_instead_of_trusting_payload(
    user, account, stripe, client, settings
):
    stripe.subscriptions = [subscription()]
    billing.schedule_plan(user, "coach")
    payload = event(kind="subscription_schedule.updated")
    payload["data"]["object"]["phases"] = [{"items": [{"price": "price_injected"}]}]
    assert deliver(client, settings, payload).status_code == 200
    account.refresh_from_db()
    assert account.scheduled_plan == "coach"
    assert not billing.coach_access(user)


def test_legacy_migration_is_read_only_by_default_then_idempotent(user, account, stripe):
    use_price(stripe, "price_legacy", 799)
    output = StringIO()
    call_command("migrate_pro_prices", stdout=output)
    assert "would schedule" in output.getvalue()
    assert not posts(stripe)
    account.refresh_from_db()
    assert not account.schedule_id
    call_command("migrate_pro_prices", "--apply", stdout=StringIO())
    account.refresh_from_db()
    assert account.scheduled_plan == "pro"
    assert stripe.subscriptions[0]["items"]["data"][0]["price"]["id"] == "price_legacy"
    stripe.request.reset_mock()
    call_command("migrate_pro_prices", "--apply", stdout=StringIO())
    assert not posts(stripe)


@pytest.mark.parametrize("failure_point", ["creation_response", "phase_update"])
def test_legacy_migration_recovers_interrupted_schedule(user, account, stripe, failure_point):
    use_price(stripe, "price_legacy", 799)
    handler = stripe.request.side_effect
    fail = True

    def interrupt(method, url, **kwargs):
        nonlocal fail
        if (
            fail
            and failure_point == "phase_update"
            and method == "POST"
            and url.endswith("/sub_sched_fixture")
        ):
            fail = False
            raise requests.Timeout()
        response = handler(method, url, **kwargs)
        if (
            fail
            and failure_point == "creation_response"
            and method == "POST"
            and url.endswith("/subscription_schedules")
        ):
            fail = False
            raise requests.Timeout()
        return response

    stripe.request.side_effect = interrupt
    with pytest.raises(billing.StripeFailure):
        billing.migrate_legacy_price(account.pk, dry_run=False)
    assert len(stripe.schedules) == 1
    billing.reconcile_user(user)
    account.refresh_from_db()
    assert account.schedule_id == stripe.schedules[0]["id"]
    assert not account.scheduled_plan
    stripe.request.reset_mock()
    assert billing.migrate_legacy_price(account.pk) == "would schedule"
    assert not posts(stripe)
    assert billing.migrate_legacy_price(account.pk, dry_run=False) == "scheduled"
    account.refresh_from_db()
    assert account.scheduled_plan == "pro"
    assert len(stripe.schedules) == 1
    assert stripe.schedules[0]["phases"][1]["items"][0]["price"] == "price_monthly"


def test_legacy_migration_does_not_adopt_unowned_empty_schedule(account, stripe):
    use_price(stripe, "price_legacy", 799)
    sub = stripe.subscriptions[0]
    sub["schedule"] = "sub_sched_other"
    stripe.schedules = [
        {
            "id": "sub_sched_other",
            "customer": sub["customer"],
            "subscription": sub["id"],
            "status": "active",
            "metadata": {},
            "phases": [],
        }
    ]
    previous = deepcopy(stripe.schedules)
    with pytest.raises(IntakeError, match="billing_schedule_exists"):
        billing.migrate_legacy_price(account.pk, dry_run=False)
    assert stripe.schedules == previous
    assert not any(call.args[1].endswith("/sub_sched_other") for call in posts(stripe))


def test_legacy_migration_preserves_remote_future_plan_after_local_rollback(user, account, stripe):
    use_price(stripe, "price_legacy", 799)
    billing.schedule_plan(user, "coach")
    BillingAccount.objects.filter(pk=account.pk).update(
        schedule_id="", scheduled_plan="", scheduled_at=None
    )
    previous = deepcopy(stripe.schedules)
    stripe.request.reset_mock()
    assert billing.migrate_legacy_price(account.pk, dry_run=False) == "skipped"
    assert not posts(stripe)
    assert stripe.schedules == previous


@pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
@pytest.mark.parametrize("current_subscription", [False, True])
def test_retired_legacy_price_does_not_block_reconciliation(
    user,
    account,
    stripe,
    settings,
    status,
    current_subscription,
):
    historical = subscription(status, price="price_legacy")
    historical["id"] = "sub_legacy"
    stripe.subscriptions = [historical]
    if current_subscription:
        stripe.subscriptions.append(subscription())
    settings.STRIPE_LEGACY_PRO_PRICE_ID = ""
    billing.reconcile_user(user)
    account.refresh_from_db()
    assert billing.paid_access(user) is current_subscription
    assert account.subscription_id == ("sub_fixture" if current_subscription else "sub_legacy")
    assert account.plan == "pro"


def test_retired_legacy_subscriber_can_purchase_again(user, account, stripe, settings):
    stripe.subscriptions = [subscription("canceled", price="price_legacy")]
    settings.STRIPE_LEGACY_PRO_PRICE_ID = ""
    assert billing.checkout(user) == stripe.session["url"]
    assert any(call.args[1].endswith("/checkout/sessions") for call in posts(stripe))


def test_retired_price_still_rejects_live_subscription(user, account, stripe, settings):
    stripe.subscriptions = [subscription(price="price_legacy")]
    settings.STRIPE_LEGACY_PRO_PRICE_ID = ""
    with pytest.raises(IntakeError, match="billing_subscription_mismatch"):
        billing.reconcile_user(user)
    assert not billing.paid_access(user)


@pytest.mark.parametrize("reason", ["cancel", "schedule", "unpaid", "new", "coach"])
def test_legacy_migration_skips_existing_intentions(user, account, stripe, reason):
    use_price(stripe, "price_legacy", 799)
    sub = stripe.subscriptions[0]
    if reason == "cancel":
        sub["cancel_at_period_end"] = True
    elif reason == "schedule":
        sub["schedule"] = "sub_sched_other"
        stripe.schedules = [
            {
                "id": "sub_sched_other",
                "customer": sub["customer"],
                "subscription": sub["id"],
                "status": "active",
                "metadata": {"application": "operator"},
                "phases": [],
            }
        ]
    elif reason == "unpaid":
        sub["status"] = "past_due"
    else:
        sub["items"]["data"][0]["price"]["id"] = (
            "price_monthly" if reason == "new" else "price_coach"
        )
    call_command("migrate_pro_prices", "--apply", stdout=StringIO())
    assert not posts(stripe)
