"""Account-specific quota and Pro sources, independent of intake services."""

from django.conf import settings
from django.utils import timezone


def monthly_limit(user):
    policy = getattr(user, "account_policy", None) if user.pk else None
    override = policy.monthly_limit_override if policy else None
    return settings.DEMO_MONTHLY_LIMIT if override is None else override


def manual_access(user):
    policy = getattr(user, "account_policy", None) if user.pk else None
    return bool(policy and policy.manual_pro_until and policy.manual_pro_until > timezone.now())


def pro_access(user):
    # Billing imports intake services, so resolve this source only when needed.
    from .billing import paid_access

    return paid_access(user) or manual_access(user)
