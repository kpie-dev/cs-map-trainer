import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class AccountPreferences(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_player_steam_id = models.CharField(
        max_length=17, blank=True, validators=[RegexValidator(r"^[0-9]{17}$")]
    )


class AccountPolicy(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_policy"
    )
    monthly_limit_override = models.PositiveIntegerField(null=True, blank=True)
    manual_pro_until = models.DateTimeField(null=True, blank=True)
    session_version = models.PositiveIntegerField(default=0)

    class Meta:
        permissions = [
            ("support_view", "View support account details"),
            ("support_email", "Send account verification and reset links"),
            ("support_manage", "Manage account limits, access and blocks"),
            ("support_billing", "Refresh account billing status"),
        ]


class CacheEntry(models.Model):
    cache_key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()
    expires = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "trainer_shared_cache"


class SupportAudit(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=32)
    reason = models.CharField(max_length=500)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    outcome = models.CharField(max_length=16)
    error_code = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["target", "-created_at"], name="support_target_time_idx"),
            models.Index(fields=["actor", "-created_at"], name="support_actor_time_idx"),
        ]


class Upload(models.Model):
    class State(models.TextChoices):
        UPLOADING = "uploading"
        QUEUED = "queued"
        RUNNING = "running"
        READY = "ready"
        UNSUPPORTED = "unsupported"
        FAILED = "failed"
        EXPIRED = "expired"
        DELETED = "deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    player_steam_id = models.CharField(max_length=17, validators=[RegexValidator(r"^[0-9]{17}$")])
    request_id = models.UUIDField()
    size_bytes = models.PositiveBigIntegerField()
    key = models.CharField(max_length=100, unique=True)
    multipart_id = models.TextField(blank=True)
    state = models.CharField(max_length=16, choices=State, default=State.UPLOADING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    dispatched_at = models.DateTimeField(null=True)
    quota_charged = models.BooleanField(default=True)
    cleanup_pending = models.BooleanField(default=True)
    cleanup_error = models.CharField(max_length=64, blank=True)
    input_deleted_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=64, blank=True)
    report = models.JSONField(null=True)
    scripts = models.JSONField(null=True)
    selection = models.JSONField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "request_id"], name="unique_upload_request"),
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(state__in=["uploading", "queued", "running"]),
                name="one_active_upload_per_account",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=8, size_bytes__lte=1024**3),
                name="technical_demo_size",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "created_at"], name="trainer_upl_owner_i_50063e_idx"),
            models.Index(fields=["player_steam_id", "owner"], name="trainer_player_owner_idx"),
        ]


class PracticeReview(models.Model):
    class Rating(models.TextChoices):
        DONE = "done", "Done"
        EASY = "easy", "Easy"
        HARD = "hard", "Hard"
        IRRELEVANT = "irrelevant", "Not useful"

    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="practice_reviews")
    scenario_id = models.CharField(max_length=128)
    rating = models.CharField(max_length=16, choices=Rating)
    reviewed_at = models.DateTimeField()
    due_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["upload", "scenario_id"], name="unique_scenario_review"
            ),
            models.CheckConstraint(
                condition=(
                    Q(rating="irrelevant", due_at__isnull=True)
                    | Q(rating__in=["done", "easy", "hard"], due_at__isnull=False)
                ),
                name="valid_practice_schedule",
            ),
        ]


class BillingAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="billing_account",
    )
    customer_id = models.CharField(max_length=128, unique=True, null=True)
    checkout_id = models.CharField(max_length=128, blank=True)
    checkout_generation = models.PositiveIntegerField(default=0)
    subscription_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=32, blank=True)
    paid_until = models.DateTimeField(null=True)
    cancel_at_period_end = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True)
    closed = models.BooleanField(default=False)


class BillingEvent(models.Model):
    event_id = models.CharField(primary_key=True, max_length=128)
    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE)
    processed_at = models.DateTimeField(auto_now_add=True)
