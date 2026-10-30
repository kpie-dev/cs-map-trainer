from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .admin_access import SupportAdminSite, require_recent_admin_authentication
from .entitlements import manual_access, monthly_limit
from .models import AccountPreferences, BillingAccount, PlayerAnalysis, SupportAudit, Upload
from .services import IntakeError, month_start, quota_used
from .support import ACTIONS, SupportActionForm, can_operate, execute_action

site = SupportAdminSite(name="admin")
site.site_header = "CS Map Trainer support"
site.site_title = "Account support"
site.index_title = "User support"


class VerifiedFilter(admin.SimpleListFilter):
    title = "email verification"
    parameter_name = "verified"

    def lookups(self, request, model_admin):
        return [("yes", "Verified"), ("no", "Unverified")]

    def queryset(self, request, queryset):
        if self.value() in {"yes", "no"}:
            return queryset.filter(support_verified=self.value() == "yes")
        return queryset


class AccessFilter(admin.SimpleListFilter):
    title = "Pro source"
    parameter_name = "pro"

    def lookups(self, request, model_admin):
        return [("paid", "Stripe Pro"), ("manual", "Manual Pro"), ("free", "Free")]

    def queryset(self, request, queryset):
        if self.value() == "paid":
            return queryset.filter(support_paid=True)
        if self.value() == "manual":
            return queryset.filter(account_policy__manual_pro_until__gt=timezone.now())
        if self.value() == "free":
            return queryset.filter(support_paid=False).filter(
                Q(account_policy__manual_pro_until__isnull=True)
                | Q(account_policy__manual_pro_until__lte=timezone.now())
            )
        return queryset


class LimitFilter(admin.SimpleListFilter):
    title = "monthly limit"
    parameter_name = "limit"

    def lookups(self, request, model_admin):
        return [("custom", "Individual"), ("default", "Default")]

    def queryset(self, request, queryset):
        if self.value() in {"custom", "default"}:
            return queryset.filter(
                account_policy__monthly_limit_override__isnull=self.value() == "default"
            )
        return queryset


def stripe_links(account):
    if not account:
        return []
    key = settings.STRIPE_SECRET_KEY
    if key.startswith(("sk_test_", "rk_test_")):
        base = "https://dashboard.stripe.com/test/"
    elif key.startswith(("sk_live_", "rk_live_")):
        base = "https://dashboard.stripe.com/"
    else:
        return []
    links = []
    for label, section, value in (
        ("Customer in Stripe", "customers", account.customer_id),
        ("Subscription in Stripe", "subscriptions", account.subscription_id),
    ):
        if value:
            try:
                from .billing import identifier

                identifier(value)
            except ValueError:
                continue
            links.append((label, f"{base}{section}/{value}"))
    return links


class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "id",
        "is_active",
        "email_verified",
        "analyses_used",
        "effective_limit",
        "access_source",
        "subscription_status",
    )
    list_display_links = ("email",)
    list_filter = (
        "is_active",
        VerifiedFilter,
        AccessFilter,
        LimitFilter,
        "billing_account__status",
    )
    search_fields = (
        "=id",
        "email",
        "=billing_account__customer_id",
        "=billing_account__subscription_id",
    )
    search_help_text = "Email, account ID, exact SteamID64, or Stripe customer/subscription ID."
    ordering = ("-date_joined", "-pk")
    list_per_page = 30
    actions = None

    def has_module_permission(self, request):
        return request.user.has_perm("trainer.support_view")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("trainer.support_view")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        usage = (
            Upload.objects.filter(owner_id=OuterRef("pk"), quota_charged=True)
            .annotate(quota_at=Coalesce("accepted_at", "created_at"))
            .filter(quota_at__gte=month_start())
            .order_by()
            .values("owner_id")
            .annotate(total=Count("pk"))
            .values("total")
        )
        return (
            super()
            .get_queryset(request)
            .select_related("account_policy", "billing_account")
            .annotate(
                support_verified=Exists(
                    EmailAddress.objects.filter(user_id=OuterRef("pk"), verified=True)
                ),
                support_paid=Exists(
                    BillingAccount.objects.filter(
                        owner_id=OuterRef("pk"), closed=False, paid_until__gt=timezone.now()
                    )
                ),
                support_used=Coalesce(Subquery(usage), 0),
            )
        )

    def get_search_results(self, request, queryset, search_term):
        term = search_term.strip()
        if len(term) == 17 and term.isascii() and term.isdigit():
            return queryset.filter(
                Q(pk__in=Upload.objects.filter(player_steam_id=term).values("owner_id"))
                | Q(pk__in=PlayerAnalysis.objects.filter(steam_id=term).values("upload__owner_id"))
                | Q(
                    pk__in=AccountPreferences.objects.filter(last_player_steam_id=term).values(
                        "owner_id"
                    )
                )
            ), False
        return super().get_search_results(request, queryset, search_term)

    @admin.display(boolean=True)
    def email_verified(self, obj):
        return obj.support_verified

    @admin.display(description="Used this month (UTC)")
    def analyses_used(self, obj):
        return obj.support_used

    @admin.display(description="Monthly free limit")
    def effective_limit(self, obj):
        return monthly_limit(obj)

    @admin.display(description="Pro source")
    def access_source(self, obj):
        sources = []
        if obj.support_paid:
            sources.append("Stripe Coach" if obj.billing_account.plan == "coach" else "Stripe")
        if manual_access(obj):
            sources.append("Manual")
        return " + ".join(sources) or "Free"

    @admin.display(description="Stripe snapshot")
    def subscription_status(self, obj):
        account = getattr(obj, "billing_account", None)
        return account.status if account and account.status else "No subscription"

    def get_urls(self):
        return [
            path(
                "<path:object_id>/support/<str:action>/",
                self.admin_site.admin_view(self.support_action),
                name="support_action",
            ),
        ] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        if not self.has_view_permission(request):
            raise PermissionDenied
        target = self.get_object(request, object_id)
        if target is None:
            raise Http404
        now = timezone.now()
        start = month_start(now)
        reset = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        billing = getattr(target, "billing_account", None)
        policy = getattr(target, "account_policy", None)
        uploads = (
            Upload.objects.filter(owner=target)
            .prefetch_related("player_results")
            .defer("report", "scripts", "selection", "key", "multipart_id")
            .order_by("-created_at", "-pk")
        )
        steam_ids = (
            Upload.objects.filter(owner=target)
            .order_by()
            .values_list("player_steam_id", flat=True)
            .union(
                PlayerAnalysis.objects.filter(upload__owner=target)
                .order_by()
                .values_list("steam_id", flat=True)
            )
            .order_by("player_steam_id")
        )
        preference = getattr(target, "accountpreferences", None)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Account: {target.email}",
            "opts": self.model._meta,
            "original": target,
            "target": target,
            "policy": policy,
            "billing": billing,
            "stripe_links": stripe_links(billing),
            "used": quota_used(target),
            "limit": monthly_limit(target),
            "remaining": max(0, monthly_limit(target) - quota_used(target)),
            "reset_at": reset,
            "source": self.access_source(target),
            "steam_page": Paginator(steam_ids, 20).get_page(request.GET.get("steam_page")),
            "last_steam": preference.last_player_steam_id if preference else "",
            "uploads_page": Paginator(uploads, 20).get_page(request.GET.get("uploads_page")),
            "audit_page": Paginator(
                SupportAudit.objects.filter(target=target).select_related("actor"), 20
            ).get_page(request.GET.get("audit_page")),
            "support_actions": [
                (action, label, reverse("admin:support_action", args=[target.pk, action]))
                for action, (label, _) in ACTIONS.items()
                if can_operate(request.user, target, action)
            ],
        }
        return TemplateResponse(request, "admin/support/account.html", context)

    def support_action(self, request, object_id, action):
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        if not self.has_view_permission(request):
            raise PermissionDenied
        target = self.get_object(request, object_id)
        if target is None:
            raise Http404
        if not can_operate(request.user, target, action):
            raise PermissionDenied
        response = require_recent_admin_authentication(request)
        if response is not None:
            return response
        form = SupportActionForm(request.POST if request.method == "POST" else None, action=action)
        status = 200
        if request.method == "POST" and form.is_valid():
            try:
                execute_action(request, target, action, form.cleaned_data)
            except IntakeError as error:
                form.add_error(None, f"The operation was not confirmed. Error: {error.code}")
                status = error.status
            else:
                message = (
                    "Message accepted by the mail server; delivery is not confirmed."
                    if action in {"reset_password", "verify_email"}
                    else "Operation completed."
                )
                messages.success(request, message)
                return redirect("admin:auth_user_change", target.pk)
        return TemplateResponse(
            request,
            "admin/support/action.html",
            {
                **self.admin_site.each_context(request),
                "title": ACTIONS[action][0],
                "opts": self.model._meta,
                "target": target,
                "action": action,
                "form": form,
            },
            status=status,
        )


class AuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "target", "action", "outcome", "error_code")
    list_filter = ("action", "outcome")
    search_fields = ("=actor__id", "actor__email", "=target__id", "target__email")
    list_select_related = ("actor", "target")
    readonly_fields = (
        "actor",
        "target",
        "created_at",
        "action",
        "reason",
        "before",
        "after",
        "outcome",
        "error_code",
    )
    actions = None

    def has_module_permission(self, request):
        return request.user.has_perm("trainer.support_view")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("trainer.support_view")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


site.register(get_user_model(), AccountAdmin)
site.register(SupportAudit, AuditAdmin)
