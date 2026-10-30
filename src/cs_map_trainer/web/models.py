import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class SteamIdentity(models.Model):
    steam_id = models.CharField(
        primary_key=True, max_length=17, validators=[RegexValidator(r"^[0-9]{17}$")]
    )
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


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
    identity = models.ForeignKey(SteamIdentity, on_delete=models.PROTECT)
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
            models.UniqueConstraint(
                fields=["identity", "request_id"], name="unique_upload_request"
            ),
            models.UniqueConstraint(
                fields=["identity"],
                condition=Q(state__in=["uploading", "queued", "running"]),
                name="one_active_upload_per_steam",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=8, size_bytes__lte=1024**3),
                name="technical_demo_size",
            ),
        ]
        indexes = [models.Index(fields=["identity", "created_at"])]


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
