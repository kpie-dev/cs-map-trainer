"""Restricted support operations; billing records are never manually edited."""

import logging
import smtplib
from datetime import timedelta

from allauth.account.forms import ResetPasswordForm
from allauth.account.models import EmailAddress
from allauth.core import context, ratelimit
from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from . import billing
from .identity import lock_account
from .models import AccountPolicy, BillingAccount, SupportAudit
from .services import IntakeError

logger = logging.getLogger(__name__)
EMAIL_COOLDOWN_SECONDS = 180
EMAIL_HOURLY_LIMIT = 20
ACTIONS = {
    "limit": ("Set monthly limit", "support_manage"),
    "grant_pro": ("Grant temporary Pro", "support_manage"),
    "revoke_pro": ("Revoke manual Pro", "support_manage"),
    "block": ("Block account", "support_manage"),
    "unblock": ("Unblock account", "support_manage"),
    "reset_password": ("Send password reset link", "support_email"),
    "verify_email": ("Resend email confirmation", "support_email"),
    "refresh_billing": ("Refresh from Stripe", "support_billing"),
}
MAIL_ACTIONS = {"reset_password", "verify_email"}


class SupportActionForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
    monthly_limit = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=2147483647,
        help_text="Blank restores the default limit. Zero disables free analyses, not Pro.",
    )
    pro_until = forms.DateTimeField(required=False, help_text="Future expiry date and time (UTC).")
    confirm = forms.BooleanField(label="I understand and confirm this operation.")

    def __init__(self, *args, action, **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action
        if action != "limit":
            self.fields.pop("monthly_limit")
        if action != "grant_pro":
            self.fields.pop("pro_until")
        else:
            self.fields["pro_until"].required = True

    def clean_pro_until(self):
        value = self.cleaned_data["pro_until"]
        if value is not None and value <= timezone.now():
            raise forms.ValidationError("The expiry must be in the future.")
        return value


def can_operate(actor, target, action):
    return (
        action in ACTIONS
        and actor.is_active
        and actor.is_staff
        and actor.pk != target.pk
        and not target.is_staff
        and not target.is_superuser
        and actor.has_perm("trainer.support_view")
        and actor.has_perm(f"trainer.{ACTIONS[action][1]}")
    )


def policy_snapshot(user, policy):
    result = {
        "active": user.is_active,
        "monthly_limit_override": policy.monthly_limit_override,
        "manual_pro_until": (
            policy.manual_pro_until.isoformat() if policy.manual_pro_until else None
        ),
    }
    billing_account = (
        BillingAccount.objects.filter(owner=user)
        .values(
            "status",
            "plan",
            "paid_until",
            "cancel_at_period_end",
            "synced_at",
            "scheduled_plan",
            "scheduled_at",
        )
        .first()
    )
    if billing_account:
        result["billing"] = {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in billing_account.items()
        }
    return result


def _send_email(request, target, action):
    if not target.is_active:
        raise IntakeError("account_blocked", 409)
    address = (
        EmailAddress.objects.select_for_update()
        .filter(user=target, primary=True, email__iexact=target.email)
        .first()
    )
    if address is None:
        raise IntakeError("support_primary_email_required", 409)
    if (action == "reset_password") != address.verified:
        raise IntakeError("support_email_state_mismatch", 409)
    if action == "reset_password" and not target.has_usable_password():
        raise IntakeError("support_password_unavailable", 409)
    # Fail before creating tokens or connecting to SMTP when the origin is invalid.
    billing.public_origin()
    if not ratelimit.consume(
        request,
        action="reset_password" if action == "reset_password" else "confirm_email",
        key=address.email.lower(),
    ):
        raise IntakeError("support_email_rate_limited", 429)
    request.support_mail = True
    try:
        with context.request_context(request):
            if action == "verify_email":
                address.send_confirmation(request)
            else:
                form = ResetPasswordForm({"email": address.email})
                if not form.is_valid() or [user.pk for user in form.users] != [target.pk]:
                    raise IntakeError("support_email_state_mismatch", 409)
                form.save(request)
    finally:
        del request.support_mail


def _perform(request, target, policy, action, data):
    if action == "limit":
        policy.monthly_limit_override = data["monthly_limit"]
        policy.save(update_fields=["monthly_limit_override"])
    elif action == "grant_pro":
        if data["pro_until"] <= timezone.now():
            raise IntakeError("support_invalid_expiry", 400)
        policy.manual_pro_until = data["pro_until"]
        policy.save(update_fields=["manual_pro_until"])
    elif action == "revoke_pro":
        policy.manual_pro_until = None
        policy.save(update_fields=["manual_pro_until"])
    elif action in {"block", "unblock"}:
        if action == "block":
            policy.session_version += 1
            policy.save(update_fields=["session_version"])
        target.is_active = action == "unblock"
        target.save(update_fields=["is_active"])
    elif action in MAIL_ACTIONS:
        _send_email(request, target, action)
    elif action == "refresh_billing":
        if (
            not BillingAccount.objects.filter(owner=target, closed=False, customer_id__isnull=False)
            .exclude(customer_id="")
            .exists()
        ):
            raise IntakeError("billing_customer_required", 409)
        billing.reconcile_user(target)


def execute_action(request, target, action, data):
    """Serialize policy/intake and email cooldowns using account row locks."""
    error = None
    with transaction.atomic():
        actor = lock_account(request.user)
        target = lock_account(target)
        if not can_operate(actor, target, action):
            raise PermissionDenied
        policy, _ = AccountPolicy.objects.get_or_create(owner=target)
        before = policy_snapshot(target, policy)
        try:
            with transaction.atomic():
                if action in MAIL_ACTIONS:
                    now = timezone.now()
                    attempts = SupportAudit.objects.filter(
                        action__in=MAIL_ACTIONS, outcome__in=["success", "failed"]
                    )
                    if (
                        attempts.filter(
                            target=target,
                            action=action,
                            created_at__gte=now - timedelta(seconds=EMAIL_COOLDOWN_SECONDS),
                        ).exists()
                        or attempts.filter(
                            actor=actor, created_at__gte=now - timedelta(hours=1)
                        ).count()
                        >= EMAIL_HOURLY_LIMIT
                    ):
                        raise IntakeError("support_email_rate_limited", 429)
                _perform(request, target, policy, action, data)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Support email transport failure (%s)", type(exc).__name__)
            error = IntakeError("support_email_unavailable", 503)
        except IntakeError as exc:
            error = exc
        if error:
            target.refresh_from_db()
            policy.refresh_from_db()
        SupportAudit.objects.create(
            actor=actor,
            target=target,
            action=action,
            reason=data["reason"],
            before=before,
            after=policy_snapshot(target, policy),
            outcome="failed" if error else "success",
            error_code=error.code if error else "",
        )
    if error:
        raise error
