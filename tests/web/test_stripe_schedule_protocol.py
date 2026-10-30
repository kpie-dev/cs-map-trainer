from types import SimpleNamespace
from unittest.mock import Mock

from django.utils import timezone

from cs_map_trainer.web import billing


def test_pinned_basil_schedule_uses_iterations_and_contiguous_phases(settings):
    settings.STRIPE_PRICE_ID = "price_pro"
    settings.STRIPE_COACH_PRICE_ID = "price_coach"
    settings.STRIPE_LEGACY_PRO_PRICE_ID = ""
    start = int(timezone.now().timestamp()) - 100
    boundary = start + 3600
    subscription = {
        "id": "sub_protocol",
        "items": {
            "has_more": False,
            "data": [
                {
                    "price": {"id": "price_pro"},
                    "quantity": 1,
                    "current_period_start": start,
                    "current_period_end": boundary,
                }
            ],
        },
    }
    schedule = {
        "id": "sub_sched_protocol",
        "status": "active",
        "current_phase": {"start_date": start, "end_date": boundary},
    }
    stripe = Mock()
    stripe.call.side_effect = [schedule, schedule]
    account = SimpleNamespace(save=Mock())

    billing._schedule_subscription(account, stripe, subscription, "coach")

    assert billing.API_VERSION == "2025-06-30.basil"
    create, update = stripe.call.call_args_list
    assert create.args == ("POST", "subscription_schedules", {"from_subscription": "sub_protocol"})
    assert update.args[:2] == ("POST", "subscription_schedules/sub_sched_protocol")
    data = update.args[2]
    assert data["phases[0][start_date]"] == start
    assert data["phases[0][end_date]"] == data["phases[1][start_date]"] == boundary
    assert data["phases[0][items][0][price]"] == "price_pro"
    assert data["phases[1][items][0][price]"] == "price_coach"
    assert data["phases[1][iterations]"] == 1
    assert not any("[duration]" in key for key in data)
    assert "phases[1][end_date]" not in data
    assert data["end_behavior"] == "release"
    assert data["proration_behavior"] == "none"
    assert data["phases[0][proration_behavior]"] == "none"
    assert data["phases[1][proration_behavior]"] == "none"
    account.save.assert_called_once()


def test_release_preserves_cancellation_and_accepts_detached_response():
    subscription = {
        "id": "sub_protocol",
        "customer": "cus_protocol",
        "schedule": "sub_sched_protocol",
        "status": "active",
        "cancel_at_period_end": True,
    }
    stripe = Mock()
    stripe.call.side_effect = [
        {
            "id": "sub_sched_protocol",
            "customer": "cus_protocol",
            "subscription": "sub_protocol",
            "status": "active",
        },
        {
            "id": "sub_sched_protocol",
            "customer": "cus_protocol",
            "subscription": None,
            "released_subscription": "sub_protocol",
            "status": "released",
        },
    ]
    account = SimpleNamespace(schedule_id="", scheduled_plan="", scheduled_at=None)

    billing._sync_schedule(account, stripe, subscription)

    assert stripe.call.call_args.args == (
        "POST",
        "subscription_schedules/sub_sched_protocol/release",
        {"preserve_cancel_date": "true"},
    )
    assert not account.schedule_id
    assert not account.scheduled_plan
    assert account.scheduled_at is None
