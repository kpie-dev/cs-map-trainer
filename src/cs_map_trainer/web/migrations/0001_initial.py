import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SteamIdentity",
            fields=[
                (
                    "steam_id",
                    models.CharField(
                        max_length=17,
                        primary_key=True,
                        serialize=False,
                        validators=[django.core.validators.RegexValidator("^[0-9]{17}$")],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.OneToOneField(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Upload",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("request_id", models.UUIDField()),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("key", models.CharField(max_length=100, unique=True)),
                ("multipart_id", models.TextField(blank=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("uploading", "Uploading"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("ready", "Ready"),
                            ("unsupported", "Unsupported"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                            ("deleted", "Deleted"),
                        ],
                        default="uploading",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(null=True)),
                ("started_at", models.DateTimeField(null=True)),
                ("finished_at", models.DateTimeField(null=True)),
                ("dispatched_at", models.DateTimeField(null=True)),
                ("quota_charged", models.BooleanField(default=True)),
                ("cleanup_pending", models.BooleanField(default=True)),
                ("cleanup_error", models.CharField(blank=True, max_length=64)),
                ("input_deleted_at", models.DateTimeField(null=True)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("report", models.JSONField(null=True)),
                ("scripts", models.JSONField(null=True)),
                (
                    "identity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="trainer.steamidentity"
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["identity", "created_at"], name="trainer_upl_identit_594281_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("identity", "request_id"), name="unique_upload_request"
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("state__in", ["uploading", "queued", "running"])),
                        fields=("identity",),
                        name="one_active_upload_per_steam",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("size_bytes__gte", 8), ("size_bytes__lte", 1073741824)),
                        name="technical_demo_size",
                    ),
                ],
            },
        ),
    ]
