import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.utils import timezone

from cs_map_trainer.web import services, tasks
from cs_map_trainer.web.models import AccountPreferences, Upload
from cs_map_trainer.web.storage import R2, InvalidUpload

pytestmark = pytest.mark.django_db
STEAM = "76561198000000001"


def test_initiation_idempotent_and_conflicting_size(user, storage):
    request_id = uuid.uuid4()
    upload = services.initiate(user, request_id, 32, "76561198000000001", storage)
    assert services.initiate(user, request_id, 32, "76561198000000001", storage).pk == upload.pk
    assert Upload.objects.count() == 1
    storage.begin.assert_called_once()
    with pytest.raises(services.IntakeError, match="idempotency_conflict"):
        services.initiate(user, request_id, 33, "76561198000000001", storage)


@pytest.mark.parametrize("size", [0, 7, 1024**3 + 1, True, None, "20"])
def test_invalid_technical_sizes(user, storage, size):
    with pytest.raises(services.IntakeError, match="invalid_demo_size"):
        services.initiate(user, uuid.uuid4(), size, "76561198000000001", storage)
    storage.begin.assert_not_called()


def test_three_uploads_per_account_calendar_month(user, storage):
    for _ in range(3):
        item = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
        Upload.objects.filter(pk=item.pk).update(
            state=Upload.State.UNSUPPORTED, cleanup_pending=False
        )
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
    oldest = Upload.objects.order_by("created_at").first()
    Upload.objects.filter(pk=oldest.pk).update(
        created_at=services.month_start() - timedelta(microseconds=1)
    )
    assert services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)


def test_one_active_upload(user, storage, upload):
    with pytest.raises(services.IntakeError, match="active_upload_exists"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)


@pytest.mark.django_db(transaction=True)
def test_concurrent_intake_is_serialized_by_account(user, storage):
    def start(_):
        close_old_connections()
        try:
            owner = get_user_model().objects.get(pk=user.pk)
            try:
                return str(
                    services.initiate(owner, uuid.uuid4(), 32, "76561198000000001", storage).pk
                )
            except services.IntakeError as error:
                return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, range(2)))
    assert results.count("active_upload_exists") == 1
    assert Upload.objects.count() == 1


def test_unique_request_and_active_constraints(user, upload):
    with transaction.atomic(), pytest.raises(IntegrityError):
        Upload.objects.create(
            owner=user,
            player_steam_id=upload.player_steam_id,
            request_id=uuid.uuid4(),
            size_bytes=32,
            key="other.dem",
            expires_at=upload.expires_at,
        )
    Upload.objects.filter(pk=upload.pk).update(state="ready")
    with transaction.atomic(), pytest.raises(IntegrityError):
        Upload.objects.create(
            owner=user,
            player_steam_id=STEAM,
            request_id=upload.request_id,
            size_bytes=32,
            key="duplicate.dem",
            state="ready",
            expires_at=upload.expires_at,
        )


def test_complete_enqueues_after_commit_once(
    user, upload, storage, django_capture_on_commit_callbacks
):
    with patch.object(services, "dispatch") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            services.complete(user, upload.pk, storage)
            dispatch.assert_not_called()
        services.complete(user, upload.pk, storage)
        dispatch.assert_called_once_with(upload.pk)
    upload.refresh_from_db()
    assert upload.state == Upload.State.QUEUED
    storage.complete.assert_called_once()


def test_complete_recovers_r2_commit_before_database_commit(user, upload, storage):
    storage.complete.side_effect = ClientError({"Error": {"Code": "NoSuchUpload"}}, "ListParts")
    with patch.object(services, "dispatch"):
        services.complete(user, upload.pk, storage)
    storage.verify.assert_called_once_with(upload)


def test_expired_upload_cannot_finalize(user, upload, storage):
    Upload.objects.filter(pk=upload.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(services.IntakeError, match="upload_expired"):
        services.complete(user, upload.pk, storage)
    storage.complete.assert_not_called()


def test_no_automatic_parse_retry_on_duplicate_delivery(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(tasks, "run_parser", side_effect=TimeoutError) as parser,
    ):
        tasks.process_upload(upload.pk)
        tasks.process_upload(upload.pk)
    assert parser.call_count == 1
    upload.refresh_from_db()
    assert upload.state == Upload.State.FAILED
    assert upload.quota_charged is False
    assert upload.input_deleted_at
    assert {path.name for path in tmp_path.iterdir()} == {".parser.lock"}
    storage.delete.assert_called_once()


@pytest.mark.parametrize("valid", [True, False])
def test_attempt_persists_result_then_removes_inputs(
    upload, storage, settings, tmp_path, training_report, valid
):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    report = training_report.model_dump(mode="json") if valid else None
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(tasks, "run_parser", return_value=(report, [] if valid else None)),
    ):
        tasks.process_upload(upload.pk)
    upload.refresh_from_db()
    assert upload.state == (Upload.State.READY if valid else Upload.State.UNSUPPORTED)
    assert upload.report is None
    if report is not None:
        assert upload.player_results.get().report == report
    assert upload.quota_charged
    assert upload.input_deleted_at
    assert not upload.cleanup_pending
    storage.delete.assert_called_once()


def test_cleanup_failure_is_visible_and_retried(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.FAILED)
    storage.delete.side_effect = OSError("temporary failure")
    assert not tasks.cleanup(upload, storage)
    upload.refresh_from_db()
    assert upload.cleanup_pending
    assert upload.cleanup_error == "input_cleanup_failed"
    storage.delete.side_effect = None
    assert tasks.cleanup(upload, storage)
    upload.refresh_from_db()
    assert not upload.cleanup_pending
    assert upload.cleanup_error == ""


def test_reaper_expires_upload_and_releases_quota(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with patch.object(tasks, "R2", return_value=storage):
        tasks.maintain()
    upload.refresh_from_db()
    assert upload.state == Upload.State.EXPIRED
    assert not upload.quota_charged
    assert not upload.cleanup_pending


def test_reaper_marks_lost_worker_without_retry(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.RUNNING, started_at=timezone.now() - timedelta(hours=1)
    )
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(tasks, "dispatch") as dispatch,
    ):
        tasks.maintain()
    upload.refresh_from_db()
    assert upload.error_code == "worker_lost"
    assert upload.state == Upload.State.FAILED
    assert not upload.quota_charged
    dispatch.assert_not_called()


def test_redispatch_recovers_missing_enqueue(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(tasks, "dispatch") as dispatch,
    ):
        tasks.maintain()
    dispatch.assert_called_once_with(upload.pk)


def test_enqueue_failure_keeps_durable_outbox(upload):
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with patch.object(services, "async_task", side_effect=RuntimeError):
        services.dispatch(upload.pk)
    upload.refresh_from_db()
    assert upload.state == Upload.State.QUEUED
    assert upload.dispatched_at is None


def test_parser_child_invalid_header_and_timeout(upload, settings, tmp_path):
    settings.PARSER_MEMORY_BYTES = 8 * 1024**3
    (tmp_path / "input.dem").write_bytes(b"not-a-cs2-demo")
    assert tasks.run_parser(upload, tmp_path) == (None, None)
    (tmp_path / "result.json").unlink()
    with patch(
        "cs_map_trainer.web.tasks.run_bounded", side_effect=subprocess.TimeoutExpired("x", 1)
    ):
        with pytest.raises(subprocess.TimeoutExpired):
            tasks.run_parser(upload, tmp_path)


def test_parser_child_without_home_uses_upload_scoped_awpy_directory(
    upload, settings, tmp_path, monkeypatch
):
    settings.PARSER_MEMORY_BYTES = 8 * 1024**3
    monkeypatch.setenv("HOME", "/outside-upload")
    monkeypatch.setenv("AWPY_DATA_DIR", "/outside-upload/awpy")
    (tmp_path / "input.dem").write_bytes(b"not-a-cs2-demo")
    run_bounded = tasks.run_bounded
    bootstrap = """
import os
import runpy
import sys
from pathlib import Path

def unavailable_home():
    raise RuntimeError("Could not determine home directory.")

Path.home = staticmethod(unavailable_home)
assert "HOME" not in os.environ
import awpy.data
assert awpy.data.AWPY_DATA_DIR == Path(sys.argv[1]).parent / "awpy"
runpy.run_module("cs_map_trainer.web.processor", run_name="__main__")
"""

    def run_without_home(command, env, **kwargs):
        assert env["AWPY_DATA_DIR"] == str(tmp_path / "awpy")
        return run_bounded([command[0], "-c", bootstrap, *command[3:]], env, **kwargs)

    with patch.object(tasks, "run_bounded", side_effect=run_without_home):
        assert tasks.run_parser(upload, tmp_path) == (None, None)


def test_parser_payload_cannot_inject_commands(upload, settings, tmp_path, training_report):
    report = training_report.model_dump(mode="json")
    report["player_steam_id"] = STEAM
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "report": report,
                "scripts": [{"console_line": "malicious"}],
                "error": None,
            }
        )
    )
    with patch("cs_map_trainer.web.tasks.run_bounded"):
        _, scripts = tasks.run_parser(upload, tmp_path)
    assert scripts
    assert scripts[0]["console_line"] != "malicious"


@pytest.mark.parametrize("valid", [True, False])
def test_parser_report_group_cells_use_strict_json_validation(
    upload, tmp_path, training_report, valid
):
    from pydantic import ValidationError

    report = training_report.model_dump(mode="json")
    scenario = report["scenario_document"]["scenarios"][0]
    report["groups"] = [
        {
            "group_id": "group-a",
            "observations": 1,
            "wins": 0,
            "losses": 1,
            "win_rate": 0.0,
            "player_side": scenario["player"]["side"],
            "player_weapon": scenario["player"]["weapon"],
            "opponent_weapon": scenario["opponent"]["weapon"],
            "player_cell": [-2, 1, -1] if valid else ["-2", 1, -1],
            "opponent_cell": [0, 0, 0],
            "context_limitations": [],
            "selected_scenario_ids": [scenario["scenario_id"]],
        }
    ]
    (tmp_path / "result.json").write_text(json.dumps({"report": report, "error": None}))
    with patch.object(tasks, "run_bounded"):
        if valid:
            result, scripts = tasks.run_parser(upload, tmp_path)
            assert result["groups"] == report["groups"]
            assert scripts[0]["console_line"]
        else:
            with pytest.raises(ValidationError):
                tasks.run_parser(upload, tmp_path)


def test_private_results_and_delete_history(api, user, upload):
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.READY, report={"retained": True}, scripts=[{"console_line": "test"}]
    )
    assert api.get(f"/backend/uploads/{upload.pk}/").json()["report"] == {"retained": True}
    other = get_user_model().objects.create_user("intruder", "other@example.test")
    EmailAddress.objects.create(user=other, email=other.email, verified=True)
    api.force_login(other)
    assert api.get(f"/backend/uploads/{upload.pk}/").status_code == 404
    assert api.delete(f"/backend/uploads/{upload.pk}/").status_code == 404
    api.force_login(user)
    assert api.delete(f"/backend/uploads/{upload.pk}/").status_code == 200
    assert api.get(f"/backend/uploads/{upload.pk}/").status_code == 404
    upload.refresh_from_db()
    assert upload.report is None
    assert upload.scripts is None
    assert upload.quota_charged


def test_account_delete_clears_history_but_preserves_quota_tombstone(api, user, upload):
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.READY, report={"private": True})
    response = api.post(
        "/backend/account/delete/", {"password": "some-password"}, content_type="application/json"
    )
    assert response.status_code == 200
    upload.refresh_from_db()
    assert upload.owner_id is None
    assert upload.report is None
    assert upload.quota_charged
    assert not AccountPreferences.objects.exists()
    assert not get_user_model().objects.filter(pk=user.pk).exists()


def test_account_deletion_blocks_during_active_attempt(user, upload):
    with pytest.raises(services.IntakeError, match="processing_in_progress"):
        services.delete_account(user)


def test_only_verified_email_is_required(client, user, storage):
    assert client.get("/backend/history/").status_code == 403
    client.force_login(user)
    EmailAddress.objects.filter(user=user).update(verified=False)
    assert client.get("/backend/history/").status_code == 403
    EmailAddress.objects.filter(user=user).update(verified=True)
    assert client.get("/backend/history/").status_code == 200
    assert services.initiate(user, uuid.uuid4(), 32, STEAM, storage)


def test_csrf_required_for_intake(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert (
        client.post("/backend/uploads/", "{}", content_type="application/json").status_code == 403
    )


def test_intake_uses_client_player_steam_id(api, storage):
    with patch("cs_map_trainer.web.views.R2", return_value=storage):
        response = api.post(
            "/backend/uploads/",
            {
                "request_id": str(uuid.uuid4()),
                "size_bytes": 32,
                "has_upload_rights": True,
                "player_steam_id": "76561198000000009",
            },
            content_type="application/json",
        )
    assert response.status_code == 201
    assert Upload.objects.get().player_steam_id == "76561198000000009"
    assert response.json()["player_steam_id"] == "76561198000000009"
    assert response.json()["method"] == "PUT"


@pytest.mark.parametrize("payload", ["[]", "{", "null"])
def test_invalid_body_is_explicit(api, payload):
    assert (
        api.post("/backend/uploads/", payload, content_type="application/json").status_code == 400
    )


def test_public_registration_sends_verification_email(client):
    response = client.post(
        "/accounts/signup/",
        {
            "email": "new@example.test",
            "password1": "a-reasonable-passphrase-8129",
            "password2": "a-reasonable-passphrase-8129",
        },
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    owner = get_user_model().objects.get(email="new@example.test")
    assert not EmailAddress.objects.get(user=owner).verified
    assert client.get("/backend/history/").status_code == 403


def test_login_template_and_steam_routes(client, api):
    assert Client().get("/accounts/login/").status_code == 200
    for path in [
        "/accounts/steam/login/",
        "/accounts/steam/login/callback/",
        "/accounts/openid/login/",
        "/accounts/social/connections/",
    ]:
        assert api.get(path).status_code == 404
        assert api.post(path, {"process": "connect"}).status_code == 404


def test_signed_part_binds_actual_content_length(upload):
    url = R2().sign(upload)
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(url).query)
    assert "content-length" in query["X-Amz-SignedHeaders"][0].split(";")
    assert query["partNumber"] == ["1"]
    assert query["uploadId"] == [upload.multipart_id]


def test_signed_part_uses_public_endpoint_without_changing_backend(upload, settings):
    from urllib.parse import parse_qs, urlparse

    settings.R2_ENDPOINT = "http://storage:5000"
    settings.R2_PUBLIC_ENDPOINT = "http://localhost:5001"
    storage = R2()
    url = urlparse(storage.sign(upload))
    assert storage.client.meta.endpoint_url == "http://storage:5000"
    assert storage.upload_client.meta.endpoint_url == "http://localhost:5001"
    assert url.netloc == "localhost:5001"
    assert url.path == f"/{settings.R2_BUCKET}/{upload.key}"
    query = parse_qs(url.query)
    assert "content-length" in query["X-Amz-SignedHeaders"][0].split(";")
    assert query["uploadId"] == [upload.multipart_id]
    assert query["partNumber"] == ["1"]


def test_signing_defaults_to_backend_endpoint(settings):
    settings.R2_PUBLIC_ENDPOINT = ""
    storage = R2()
    assert storage.upload_client is storage.client


@pytest.mark.parametrize("parts", [[], [{"PartNumber": 1, "Size": 33, "ETag": "x"}]])
def test_r2_rejects_incorrect_part_size(upload, parts):
    storage = R2()
    storage.client = Mock()
    storage.client.list_parts.return_value = {"Parts": parts}
    with pytest.raises(InvalidUpload):
        storage.complete(upload)
    storage.client.complete_multipart_upload.assert_not_called()


def test_r2_completion_uses_server_listed_part(upload):
    storage = R2()
    storage.client = Mock()
    storage.client.list_parts.return_value = {
        "Parts": [{"PartNumber": 1, "Size": 32, "ETag": "server-etag"}],
    }
    storage.client.head_object.return_value = {"ContentLength": 32}
    storage.complete(upload)
    assert storage.client.complete_multipart_upload.call_args.kwargs["MultipartUpload"] == {
        "Parts": [{"PartNumber": 1, "ETag": "server-etag"}]
    }


def test_r2_cleanup_aborts_before_deleting_object(upload):
    storage = R2()
    storage.client = Mock()
    storage.client.abort_multipart_upload.side_effect = ClientError(
        {"Error": {"Code": "NoSuchUpload"}}, "AbortMultipartUpload"
    )
    storage.delete(upload)
    storage.client.delete_object.assert_called_once_with(Bucket="test-inputs", Key=upload.key)


def test_r2_download_rejects_oversize_stream(upload, tmp_path):
    storage = R2()
    storage.client = Mock()
    storage.client.get_object.return_value = {
        "ContentLength": 32,
        "Body": StreamingBody(BytesIO(b"x" * 33), 33),
    }
    with pytest.raises(InvalidUpload, match="exceeded"):
        storage.download(upload, tmp_path / "input.dem")


def test_orphan_work_directory_removed(settings, tmp_path, storage):
    settings.WORK_ROOT = tmp_path
    orphan = tmp_path / str(uuid.uuid4())
    orphan.mkdir()
    (orphan / "input.dem").write_bytes(b"orphan")
    with patch.object(tasks, "R2", return_value=storage):
        tasks.clean_orphans(timezone.now())
    assert not orphan.exists()


def test_real_parser_process_is_killed_at_wall_timeout(settings):
    settings.PARSER_TIMEOUT_SECONDS = 0.1
    with pytest.raises(subprocess.TimeoutExpired):
        tasks.run_bounded([sys.executable, "-c", "import time; time.sleep(10)"], os.environ.copy())


def test_real_parser_process_is_killed_at_rss_limit(settings):
    settings.PARSER_MEMORY_BYTES = 1
    with pytest.raises(MemoryError):
        tasks.run_bounded([sys.executable, "-c", "import time; time.sleep(10)"], os.environ.copy())


def test_expired_account_tombstone_is_removed_only_after_window(
    user, upload, storage, settings, tmp_path
):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.READY)
    services.delete_account(user)
    with patch.object(tasks, "R2", return_value=storage):
        tasks.maintain()
    assert Upload.objects.filter(pk=upload.pk).exists()
    Upload.objects.filter(pk=upload.pk).update(
        created_at=services.month_start() - timedelta(microseconds=1)
    )
    with patch.object(tasks, "R2", return_value=storage):
        tasks.maintain()
    assert not Upload.objects.filter(pk=upload.pk).exists()


def test_completed_history_does_not_expire(user, upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.READY,
        created_at=timezone.now() - timedelta(days=365),
        report={"saved": True},
        scripts=[{"console_line": "saved"}],
    )
    with patch.object(tasks, "R2", return_value=storage):
        tasks.maintain()
    upload.refresh_from_db()
    assert upload.report == {"saved": True}
    assert upload.scripts == [{"console_line": "saved"}]


def test_complete_invalid_recovered_object_returns_explicit_error(user, upload, storage):
    storage.complete.side_effect = ClientError({"Error": {"Code": "NoSuchUpload"}}, "ListParts")
    storage.verify.side_effect = InvalidUpload("Wrong size")
    with pytest.raises(services.IntakeError, match="invalid_uploaded_object"):
        services.complete(user, upload.pk, storage)


@pytest.mark.django_db(transaction=True)
def test_real_orm_queue_dispatch_is_persistent(upload):
    from django_q.models import OrmQ

    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    services.dispatch(upload.pk)
    upload.refresh_from_db()
    assert upload.dispatched_at
    assert OrmQ.objects.count() == 1


def test_monthly_limit_counts_acceptance_not_an_older_reservation(user, storage):
    for _ in range(3):
        item = services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
        Upload.objects.filter(pk=item.pk).update(
            state=Upload.State.READY,
            cleanup_pending=False,
            created_at=services.month_start() - timedelta(microseconds=1),
            accepted_at=timezone.now(),
        )
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)


def test_missing_linked_player_is_explicit_and_charged(upload, storage, settings, tmp_path):
    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(
            tasks, "run_parser", side_effect=tasks.DemoRejected("linked_player_not_in_demo")
        ),
    ):
        tasks.process_upload(upload.pk)
    upload.refresh_from_db()
    assert upload.state == Upload.State.UNSUPPORTED
    assert upload.error_code == "linked_player_not_in_demo"
    assert upload.quota_charged
    assert upload.input_deleted_at


def test_upload_to_persistent_private_commands_flow(
    api, storage, settings, tmp_path, training_report, django_capture_on_commit_callbacks
):
    settings.WORK_ROOT = tmp_path
    storage.download.side_effect = lambda upload, path: path.write_bytes(b"synthetic-input")

    def produce_result(command, env, *, lock_fd=None):
        from pathlib import Path

        Path(command[-1]).write_text(
            json.dumps(
                {
                    "error": None,
                    "report": training_report.model_dump(mode="json"),
                }
            )
        )

    with patch("cs_map_trainer.web.views.R2", return_value=storage):
        accepted = api.post(
            "/backend/uploads/",
            {
                "request_id": str(uuid.uuid4()),
                "size_bytes": 32,
                "has_upload_rights": True,
                "player_steam_id": STEAM,
            },
            content_type="application/json",
        )
    upload_id = accepted.json()["id"]
    with patch.object(services, "R2", return_value=storage):
        with django_capture_on_commit_callbacks(execute=True):
            assert api.post(f"/backend/uploads/{upload_id}/complete/").status_code == 200
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(tasks, "run_bounded", side_effect=produce_result),
    ):
        tasks.process_upload(upload_id)
    result = api.get(f"/backend/uploads/{upload_id}/").json()
    assert result["state"] == Upload.State.READY
    assert result["report"]["player_steam_id"] == STEAM
    assert result["scripts"][0]["console_line"]
    assert result["compatibility"] == "unverified_in_game"
    assert result["cleanup_pending"] is False
    assert {path.name for path in tmp_path.iterdir()} == {".parser.lock"}
    storage.delete.assert_called_once()
    scenario_id = result["report"]["scenario_document"]["scenarios"][0]["scenario_id"]
    with (
        patch.object(tasks, "run_parser", side_effect=AssertionError("Must not parse again")),
        patch.object(services, "R2", side_effect=AssertionError("Must not use storage")),
    ):
        response = api.post(
            f"/backend/uploads/{upload_id}/selection/",
            {"include": [scenario_id], "reject": []},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["selected_scenario_ids"] == [scenario_id]
        assert api.get(f"/backend/uploads/{upload_id}/pack/").status_code == 200
        exported = api.get(f"/backend/uploads/{upload_id}/scenarios/{scenario_id}/export/").json()
        assert exported["console_line"] == result["scripts"][0]["console_line"]


def test_new_upload_waits_until_previous_input_was_deleted(user, upload, storage):
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.FAILED, quota_charged=False, cleanup_pending=True
    )
    with pytest.raises(services.IntakeError, match="input_cleanup_pending"):
        services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)
    Upload.objects.filter(pk=upload.pk).update(cleanup_pending=False)
    assert services.initiate(user, uuid.uuid4(), 32, "76561198000000001", storage)


def test_busy_inherited_parser_slot_leaves_upload_queued(upload, storage, settings, tmp_path):
    from cs_map_trainer.web.processes import parser_slot

    settings.WORK_ROOT = tmp_path
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with parser_slot(tmp_path), patch.object(tasks, "R2", return_value=storage):
        tasks.process_upload(upload.pk)
    upload.refresh_from_db()
    assert upload.state == Upload.State.QUEUED
    assert upload.started_at is None
    storage.download.assert_not_called()


def test_profile_migration_removes_only_steam_extra_fields(user):
    from importlib import import_module

    from django.apps import apps
    from django.db import connection

    steam = SocialAccount.objects.create(
        user=user,
        provider="steam",
        uid=STEAM,
        extra_data={"steamid": STEAM, "personaname": "synthetic-legacy-name"},
    )
    unrelated = SocialAccount.objects.create(
        user=user,
        provider="unrelated",
        uid="synthetic-other",
        extra_data={"keep": True},
    )
    migration = import_module("cs_map_trainer.web.migrations.0002_minimize_steam_profiles")
    migration.minimize_steam_profiles(apps, SimpleNamespace(connection=connection))
    steam.refresh_from_db()
    unrelated.refresh_from_db()
    assert steam.extra_data == {"steamid": STEAM}
    assert unrelated.extra_data == {"keep": True}
