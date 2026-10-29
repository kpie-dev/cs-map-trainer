import json
import uuid
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from cs_map_trainer.exporting import export_scenario
from cs_map_trainer.packs import build_pack, load_scenarios
from cs_map_trainer.web import services, tasks
from cs_map_trainer.web.models import Upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready_upload(upload, training_report):
    report = training_report.model_dump(mode="json")
    second = deepcopy(report["scenario_document"]["scenarios"][0])
    second["scenario_id"] = "second-scenario"
    report["scenario_document"]["scenarios"].append(second)
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.READY,
        report=report,
        cleanup_pending=False,
        input_deleted_at=timezone.now(),
    )
    upload.refresh_from_db()
    return upload


def ids(upload):
    return [item["scenario_id"] for item in upload.report["scenario_document"]["scenarios"]]


def selection_url(upload):
    return f"/backend/uploads/{upload.pk}/selection/"


def pack_url(upload):
    return f"/backend/uploads/{upload.pk}/pack/"


def export_url(upload):
    return f"/backend/uploads/{upload.pk}/scenarios/{ids(upload)[0]}/export/"


def test_default_selection_and_full_replacement(api, ready_upload):
    url = selection_url(ready_upload)
    available = ids(ready_upload)
    assert api.get(url).json() == {
        "include": None,
        "reject": [],
        "available_scenario_ids": available,
        "selected_scenario_ids": available,
        "compatibility": "unverified_in_game",
    }
    choice = {"include": [available[1]], "reject": [available[0]]}
    response = api.post(url, choice, content_type="application/json")
    assert response.status_code == 200
    ready_upload.refresh_from_db()
    assert ready_upload.selection == choice
    assert api.get(url).json() == response.json()
    detail = api.get(f"/backend/uploads/{ready_upload.pk}/").json()
    assert detail["selection"] == choice
    assert detail["report"] == ready_upload.report
    assert "selection" not in api.get("/backend/history/").json()["uploads"][0]

    response = api.post(url, {"include": None, "reject": []}, content_type="application/json")
    assert response.json()["selected_scenario_ids"] == available
    response = api.post(
        url, {"include": available[::-1], "reject": []}, content_type="application/json"
    )
    assert response.json()["selected_scenario_ids"] == available
    response = api.post(
        url, {"include": None, "reject": [available[0]]}, content_type="application/json"
    )
    assert response.json()["selected_scenario_ids"] == [available[1]]


@pytest.mark.parametrize(
    "choice",
    [
        {"include": [], "reject": []},
        {"include": ["unknown"], "reject": []},
        {"include": None, "reject": ["unknown"]},
        {"include": ["second-scenario", "second-scenario"], "reject": []},
        {"include": None, "reject": ["second-scenario", "second-scenario"]},
        {"include": ["second-scenario"], "reject": ["second-scenario"]},
    ],
)
def test_invalid_selection_leaves_previous_choice(api, ready_upload, choice):
    previous = {"include": ["second-scenario"], "reject": []}
    services.save_training_selection(ready_upload.owner, ready_upload.pk, previous)
    response = api.post(selection_url(ready_upload), choice, content_type="application/json")
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_scenario_selection"}
    ready_upload.refresh_from_db()
    assert ready_upload.selection == previous


def test_rejecting_all_is_explicit(api, ready_upload):
    response = api.post(
        selection_url(ready_upload),
        {"include": None, "reject": ids(ready_upload)},
        content_type="application/json",
    )
    assert response.json() == {"error": "invalid_scenario_selection"}
    assert response.status_code == 400


@pytest.mark.parametrize(
    "choice",
    [
        {},
        {"include": None},
        {"reject": []},
        {"include": "second-scenario", "reject": []},
        {"include": [1], "reject": []},
        {"include": [True], "reject": []},
        {"include": ["../../invalid"], "reject": []},
        {"include": None, "reject": None},
        {"include": None, "reject": "second-scenario"},
        {"include": None, "reject": [], "console_line": "say injected"},
    ],
)
def test_selection_payload_is_strict(api, ready_upload, choice):
    response = api.post(selection_url(ready_upload), choice, content_type="application/json")
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_selection_payload"}
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


@pytest.mark.parametrize("raw_body", ["[]", "{", "null"])
def test_invalid_selection_json(api, ready_upload, raw_body):
    response = api.post(selection_url(ready_upload), raw_body, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.parametrize("include_cfg", [False, True])
def test_pack_uses_saved_selection_and_existing_builder(api, ready_upload, include_cfg):
    available = ids(ready_upload)
    choice = {"include": None, "reject": [available[0]]}
    services.save_training_selection(ready_upload.owner, ready_upload.pk, choice)
    response = api.get(pack_url(ready_upload), {"include_cfg": str(include_cfg).lower()})
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"] == (
        f'attachment; filename="training-{ready_upload.pk}.zip"'
    )
    document = load_scenarios(json.dumps(ready_upload.report).encode())
    assert (
        response.content
        == build_pack(document, reject=choice["reject"], include_cfg=include_cfg).archive
    )
    with ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["available_scenario_ids"] == available
        assert manifest["selected_scenario_ids"] == [available[1]]
        assert manifest["rejected_scenario_ids"] == [available[0]]
        assert manifest["omitted_scenario_ids"] == [available[0]]
        assert manifest["compatibility"] == "unverified_in_game"
        assert ("cfg/scenario-0001.cfg" in archive.namelist()) is include_cfg
        assert len(archive.read("console/scenario-0001.txt").decode().splitlines()) == 1


def test_pack_without_parameters_defaults_to_no_cfg(api, ready_upload):
    response = api.get(pack_url(ready_upload))
    with ZipFile(BytesIO(response.content)) as archive:
        assert not any(name.startswith("cfg/") for name in archive.namelist())
        assert len(json.loads(archive.read("scenarios.json"))["scenarios"]) == 2


def test_single_export_ignores_pack_choice_and_untrusted_saved_scripts(api, ready_upload):
    services.save_training_selection(
        ready_upload.owner, ready_upload.pk, {"include": ["second-scenario"], "reject": []}
    )
    Upload.objects.filter(pk=ready_upload.pk).update(scripts=[{"console_line": "say injected"}])
    document = load_scenarios(json.dumps(ready_upload.report).encode())
    expected = export_scenario(document.scenarios[0])
    result = api.get(export_url(ready_upload)).json()
    assert result["console_line"] == expected.console_line
    assert len(result["console_line"].splitlines()) == 1
    assert result["compatibility"] == "unverified_in_game"
    assert result["exporter_version"]
    assert result["limitations"] == document.scenarios[0].limitations
    assert result["source"] == document.scenarios[0].source.model_dump()
    assert result["assumptions"]
    assert result["session_changes"]
    response = api.get(export_url(ready_upload), {"format": "cfg"})
    assert response.content.decode() == expected.cfg
    assert response["Content-Disposition"] == 'attachment; filename="scenario.cfg"'
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    missing = f"/backend/uploads/{ready_upload.pk}/scenarios/unknown/export/"
    assert api.get(missing).json() == {"error": "scenario_not_found"}
    assert api.get(missing).status_code == 404


@pytest.mark.parametrize(
    ("endpoint", "query"),
    [
        ("pack", "?include_cfg=1"),
        ("pack", "?include_cfg="),
        ("pack", "?include_cfg=true&include_cfg=false"),
        ("pack", "?include_cfg=True"),
        ("pack", "?include=second-scenario"),
        ("export", "?format=txt"),
        ("export", "?format="),
        ("export", "?format=cfg&format=json"),
        ("export", "?steam_id=76561198000000009"),
    ],
)
def test_invalid_export_parameters_are_not_ignored(api, ready_upload, endpoint, query):
    url = pack_url(ready_upload) if endpoint == "pack" else export_url(ready_upload)
    response = api.get(url + query)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_export_parameters"}


@pytest.mark.parametrize("target", ["foreign", "deleted", "missing"])
def test_training_routes_do_not_expose_other_or_deleted_results(api, ready_upload, target):
    paths = [selection_url(ready_upload), pack_url(ready_upload), export_url(ready_upload)]
    if target == "foreign":
        other = get_user_model().objects.create_user("other", "other@example.test")
        EmailAddress.objects.create(user=other, email=other.email, verified=True)
        api.force_login(other)
    elif target == "deleted":
        services.delete_history(ready_upload.owner, ready_upload.pk)
    else:
        paths = [path.replace(str(ready_upload.pk), str(uuid.uuid4())) for path in paths]
    for path in paths:
        response = api.get(path)
        assert response.status_code == 404
        assert response.json() == {"error": "not_found"}
        assert "no-store" in response["Cache-Control"]
    response = api.post(paths[0], {"include": None, "reject": []}, content_type="application/json")
    assert response.status_code == 404


@pytest.mark.parametrize("verified", [False, True])
def test_training_routes_require_verified_session(client, user, ready_upload, verified):
    if verified:
        client.force_login(user)
        EmailAddress.objects.filter(user=user).update(verified=False)
    for path in (selection_url(ready_upload), pack_url(ready_upload), export_url(ready_upload)):
        assert client.get(path).status_code == 403
    assert (
        client.post(
            selection_url(ready_upload),
            {"include": None, "reject": []},
            content_type="application/json",
        ).status_code
        == 403
    )


def test_selection_write_requires_csrf_and_reads_do_not_mutate(user, ready_upload):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    choice = {"include": ["second-scenario"], "reject": []}
    assert (
        client.post(
            selection_url(ready_upload), choice, content_type="application/json"
        ).status_code
        == 403
    )
    client.get("/backend/history/")
    assert (
        client.post(
            selection_url(ready_upload),
            choice,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        ).status_code
        == 200
    )
    for path in (selection_url(ready_upload), pack_url(ready_upload), export_url(ready_upload)):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]
        assert (
            client.put(path, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code == 405
        )
    ready_upload.refresh_from_db()
    assert ready_upload.selection == choice


@pytest.mark.parametrize(
    "state",
    [
        Upload.State.UPLOADING,
        Upload.State.QUEUED,
        Upload.State.RUNNING,
        Upload.State.FAILED,
        Upload.State.UNSUPPORTED,
        Upload.State.EXPIRED,
    ],
)
def test_nonready_results_do_not_export(api, ready_upload, state):
    Upload.objects.filter(pk=ready_upload.pk).update(state=state)
    for path in (selection_url(ready_upload), pack_url(ready_upload), export_url(ready_upload)):
        response = api.get(path)
        assert response.status_code == 409
        assert response.json() == {"error": "result_not_ready"}


def test_report_without_candidates_is_not_an_empty_pack(api, ready_upload):
    path = export_url(ready_upload)
    ready_upload.report.update(status="no_eligible_duels", scenario_document=None)
    ready_upload.save(update_fields=["report"])
    for url in (selection_url(ready_upload), pack_url(ready_upload), path):
        response = api.get(url)
        assert response.status_code == 409
        assert response.json() == {"error": "no_training_candidates"}


@pytest.mark.parametrize("corruption", ["schema", "player", "source", "contradictory_status"])
def test_invalid_saved_report_is_an_explicit_failure(api, ready_upload, corruption, caplog):
    path = export_url(ready_upload)
    if corruption == "schema":
        ready_upload.report = {"not": "a report"}
    elif corruption == "player":
        ready_upload.report["player_steam_id"] = "76561198000000009"
    elif corruption == "source":
        ready_upload.report["scenario_document"]["scenarios"][0]["source"]["demo_sha256"] = "f" * 64
    else:
        ready_upload.report["status"] = "no_eligible_duels"
    ready_upload.save(update_fields=["report"])
    for url in (selection_url(ready_upload), pack_url(ready_upload), path):
        response = api.get(url)
        assert response.status_code == 500
        assert response.json() == {"error": "invalid_saved_report"}
    assert str(ready_upload.pk) in caplog.text


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"include": None, "reject": None},
        {"include": ["unknown"], "reject": []},
    ],
)
def test_invalid_saved_selection_is_not_silently_reset(api, ready_upload, selection):
    Upload.objects.filter(pk=ready_upload.pk).update(selection=selection)
    for url in (selection_url(ready_upload), pack_url(ready_upload)):
        response = api.get(url)
        assert response.status_code == 500
        assert response.json() == {"error": "invalid_saved_selection"}
    response = api.post(
        selection_url(ready_upload),
        {"include": None, "reject": []},
        content_type="application/json",
    )
    assert response.status_code == 200


def test_unsupported_scenario_fails_entire_pack_until_rejected(api, ready_upload):
    first, second = ids(ready_upload)
    ready_upload.report["scenario_document"]["scenarios"][0]["player"]["view_angles"]["roll"] = 1
    ready_upload.save(update_fields=["report"])
    assert (
        api.post(
            selection_url(ready_upload),
            {"include": [first, second], "reject": []},
            content_type="application/json",
        ).status_code
        == 200
    )
    for url in (pack_url(ready_upload), export_url(ready_upload)):
        response = api.get(url)
        assert response.status_code == 422
        assert response.json() == {"error": "scenario_not_exportable"}
    response = api.post(
        selection_url(ready_upload),
        {"include": None, "reject": [first]},
        content_type="application/json",
    )
    assert response.status_code == 200
    response = api.get(pack_url(ready_upload))
    with ZipFile(BytesIO(response.content)) as archive:
        assert json.loads(archive.read("manifest.json"))["selected_scenario_ids"] == [second]


def test_selection_and_export_need_neither_demo_storage_nor_parser(api, ready_upload):
    with (
        patch.object(services, "R2", side_effect=AssertionError("R2 must not be used")),
        patch("cs_map_trainer.web.views.R2", side_effect=AssertionError("R2 must not be used")),
        patch.object(tasks, "R2", side_effect=AssertionError("R2 must not be used")),
        patch.object(tasks, "run_parser", side_effect=AssertionError("Must not parse again")),
        patch.object(services, "dispatch", side_effect=AssertionError("Must not enqueue")),
    ):
        assert (
            api.post(
                selection_url(ready_upload),
                {"include": ["second-scenario"], "reject": []},
                content_type="application/json",
            ).status_code
            == 200
        )
        for url in (selection_url(ready_upload), pack_url(ready_upload), export_url(ready_upload)):
            assert api.get(url).status_code == 200


@pytest.mark.parametrize("delete_account", [False, True])
def test_deletion_erases_selection_without_resetting_quota(api, ready_upload, delete_account):
    services.save_training_selection(
        ready_upload.owner, ready_upload.pk, {"include": ["second-scenario"], "reject": []}
    )
    if delete_account:
        response = api.post(
            "/backend/account/delete/",
            {"password": "some-password"},
            content_type="application/json",
        )
    else:
        response = api.delete(f"/backend/uploads/{ready_upload.pk}/")
    assert response.status_code == 200
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None
    assert ready_upload.report is None
    assert ready_upload.scripts is None
    assert ready_upload.quota_charged
