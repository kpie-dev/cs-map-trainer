import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F


def copy_players(apps, schema_editor):
    database = schema_editor.connection.alias
    Upload = apps.get_model("trainer", "Upload")
    Identity = apps.get_model("trainer", "SteamIdentity")
    Preferences = apps.get_model("trainer", "AccountPreferences")
    Upload.objects.using(database).update(player_steam_id=F("identity_id"))
    for identity in Identity.objects.using(database).exclude(owner_id=None).iterator():
        Preferences.objects.using(database).create(
            owner_id=identity.owner_id, last_player_steam_id=identity.pk
        )


class Migration(migrations.Migration):
    dependencies = [
        ("trainer", "0006_alter_practicereview_rating"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountPreferences",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "last_player_steam_id",
                    models.CharField(
                        blank=True,
                        max_length=17,
                        validators=[django.core.validators.RegexValidator(r"^[0-9]{17}$")],
                    ),
                ),
                (
                    "owner",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="upload",
            name="player_steam_id",
            field=models.CharField(
                max_length=17,
                null=True,
                validators=[django.core.validators.RegexValidator(r"^[0-9]{17}$")],
            ),
        ),
        # A rollback cannot reconstruct verified ownership from user-entered SteamIDs.
        migrations.RunPython(copy_players),
        migrations.AlterField(
            model_name="upload",
            name="player_steam_id",
            field=models.CharField(
                max_length=17,
                validators=[django.core.validators.RegexValidator(r"^[0-9]{17}$")],
            ),
        ),
        migrations.RemoveConstraint(model_name="upload", name="unique_upload_request"),
        migrations.RemoveConstraint(model_name="upload", name="one_active_upload_per_steam"),
        migrations.RemoveIndex(model_name="upload", name="trainer_upl_identit_594281_idx"),
        migrations.AddConstraint(
            model_name="upload",
            constraint=models.UniqueConstraint(
                fields=("owner", "request_id"),
                name="unique_upload_request",
            ),
        ),
        migrations.AddConstraint(
            model_name="upload",
            constraint=models.UniqueConstraint(
                fields=("owner",),
                condition=models.Q(state__in=["uploading", "queued", "running"]),
                name="one_active_upload_per_account",
            ),
        ),
        migrations.AddIndex(
            model_name="upload",
            index=models.Index(
                fields=["owner", "created_at"], name="trainer_upl_owner_i_50063e_idx"
            ),
        ),
        migrations.RemoveField(model_name="upload", name="identity"),
        migrations.DeleteModel(name="SteamIdentity"),
    ]
