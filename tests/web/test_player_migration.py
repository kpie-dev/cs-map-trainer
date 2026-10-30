import uuid
from copy import deepcopy
from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from psycopg import sql


@pytest.mark.django_db(transaction=True)
def test_player_migration_preserves_existing_accounts_uploads_and_billing(django_db_blocker):
    database = f"test_player_migration_{uuid.uuid4().hex}"
    alias = database
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    config = deepcopy(connection.settings_dict)
    config["NAME"] = database
    connections.databases[alias] = config
    isolated = connections[alias]
    try:
        with django_db_blocker.unblock():
            executor = MigrationExecutor(isolated)
            before = [("trainer", "0006_alter_practicereview_rating")]
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            User = old.get_model(settings.AUTH_USER_MODEL)
            owner = User.objects.using(alias).create(username="legacy", email="legacy@example.test")
            identity = (
                old.get_model("trainer", "SteamIdentity")
                .objects.using(alias)
                .create(owner_id=owner.pk, steam_id="76561198000000001")
            )
            now = timezone.now()
            Upload = old.get_model("trainer", "Upload")
            report = {"retained": True, "player_steam_id": identity.pk}
            ready = Upload.objects.using(alias).create(
                owner_id=owner.pk,
                identity_id=identity.pk,
                request_id=uuid.uuid4(),
                size_bytes=32,
                key="legacy-ready",
                expires_at=now,
                state="ready",
                report=report,
                scripts=[],
                selection={"include": None, "reject": []},
                accepted_at=now,
                cleanup_pending=False,
            )
            active = Upload.objects.using(alias).create(
                owner_id=owner.pk,
                identity_id=identity.pk,
                request_id=uuid.uuid4(),
                size_bytes=32,
                key="legacy-active",
                expires_at=now + timedelta(hours=1),
            )
            deleted = Upload.objects.using(alias).create(
                owner_id=None,
                identity_id=identity.pk,
                request_id=uuid.uuid4(),
                size_bytes=32,
                key="legacy-deleted",
                expires_at=now,
                state="deleted",
                cleanup_pending=False,
            )
            review = (
                old.get_model("trainer", "PracticeReview")
                .objects.using(alias)
                .create(
                    upload_id=ready.pk,
                    scenario_id="legacy-scenario",
                    rating="hard",
                    reviewed_at=now,
                    due_at=now + timedelta(days=1),
                )
            )
            billing = (
                old.get_model("trainer", "BillingAccount")
                .objects.using(alias)
                .create(
                    owner_id=owner.pk,
                    customer_id="cus_legacy",
                    subscription_id="sub_legacy",
                    paid_until=now + timedelta(days=5),
                )
            )
            executor = MigrationExecutor(isolated)
            after = [("trainer", "0007_account_upload_players")]
            executor.migrate(after)
            current = executor.loader.project_state(after).apps
            NewUpload = current.get_model("trainer", "Upload")
            saved = NewUpload.objects.using(alias).get(pk=ready.pk)
            assert saved.player_steam_id == identity.pk
            assert saved.owner_id == owner.pk
            assert saved.report == report
            assert saved.selection == ready.selection
            assert saved.scripts == []
            assert saved.accepted_at == now
            assert saved.quota_charged
            assert NewUpload.objects.using(alias).get(pk=active.pk).state == "uploading"
            assert NewUpload.objects.using(alias).get(pk=deleted.pk).player_steam_id == identity.pk
            assert (
                NewUpload.objects.using(alias).filter(owner_id=owner.pk, quota_charged=True).count()
                == 2
            )
            preferences = current.get_model("trainer", "AccountPreferences")
            assert (
                preferences.objects.using(alias).get(owner_id=owner.pk).last_player_steam_id
                == identity.pk
            )
            assert (
                current.get_model("trainer", "PracticeReview")
                .objects.using(alias)
                .get(pk=review.pk)
                .due_at
                == review.due_at
            )
            paid = (
                current.get_model("trainer", "BillingAccount")
                .objects.using(alias)
                .get(pk=billing.pk)
            )
            assert paid.customer_id == "cus_legacy"
            assert paid.subscription_id == "sub_legacy"
            assert paid.paid_until == billing.paid_until
            with pytest.raises(LookupError):
                current.get_model("trainer", "SteamIdentity")
            latest = [("trainer", "0012_migrate_player_results")]
            executor = MigrationExecutor(isolated)
            executor.migrate(latest)
            migrated = executor.loader.project_state(latest).apps
            Result = migrated.get_model("trainer", "PlayerAnalysis")
            result = Result.objects.using(alias).get(upload_id=ready.pk)
            assert result.steam_id == identity.pk
            assert result.status == "ready"
            assert result.report == report
            assert result.selection == ready.selection
            assert result.scripts == []
            assert result.statistics is None
            retained = migrated.get_model("trainer", "Upload").objects.using(alias).get(pk=ready.pk)
            assert retained.report is None
            assert retained.selection is None
            assert retained.owner_id == owner.pk
            retained_review = (
                migrated.get_model("trainer", "PracticeReview")
                .objects.using(alias)
                .get(pk=review.pk)
            )
            assert retained_review.player_result_id == result.pk
            assert retained_review.due_at == review.due_at
            assert Result.objects.using(alias).get(upload_id=active.pk).status == "pending"
            executor = MigrationExecutor(isolated)
            executor.migrate(after)
            restored = executor.loader.project_state(after).apps
            assert (
                restored.get_model("trainer", "Upload").objects.using(alias).get(pk=ready.pk).report
                == report
            )
    finally:
        isolated.close()
        del connections[alias]
        del connections.databases[alias]
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
