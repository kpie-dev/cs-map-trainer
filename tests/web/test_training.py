import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from threading import Event
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cs_map_trainer.exporting import ExportError, export_scenario
from cs_map_trainer.packs import build_pack, load_scenarios
from cs_map_trainer.training_groups import training_groups
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


def checkbox_payload(upload, *, intent="download", include=None):
    return {
        "selection_ui": "checkboxes",
        "intent": intent,
        "include": ids(upload) if include is None else include,
    }


def manifest(response):
    with ZipFile(BytesIO(response.content)) as archive:
        return json.loads(archive.read("manifest.json")), archive.namelist()


def group_payload(upload, *, partial=False):
    _, document = services.training_result(upload.owner, upload.pk)
    group = training_groups(document)[0]
    data = {"selection_ui": "groups", "intent": "download", "group": [group.group_id]}
    if partial:
        data.pop("group")
        data[f"partial_{group.group_id}"] = "preserve"
        data[f"members_{group.group_id}"] = [ids(upload)[0]]
    return data, group


def test_group_checkbox_exports_every_member_and_additive_group_metadata(api, ready_upload):
    data, group = group_payload(ready_upload)
    response = api.post(reverse("selection", args=[ready_upload.pk]), data)
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        packed = json.loads(archive.read("manifest.json"))
        membership = json.loads(archive.read("training-groups.json"))
        assert packed["pack_version"] == 1
        assert set(packed["selected_scenario_ids"]) == set(ids(ready_upload))
        assert len(packed["entries"]) == 2
        assert len([name for name in archive.namelist() if name.startswith("cfg/")]) == 2
        assert membership["groups"][0]["group_id"] == group.group_id
        assert membership["groups"][0]["selected_scenario_ids"] == group.scenario_ids
    ready_upload.refresh_from_db()
    assert set(ready_upload.selection["include"]) == set(ids(ready_upload))


def test_partial_legacy_group_preserves_then_expands_all_without_losing_rejects(api, ready_upload):
    first, second = ids(ready_upload)
    services.save_training_selection(
        ready_upload.owner, ready_upload.pk, {"include": [first], "reject": [second]}
    )
    report = api.get(reverse("report", args=[ready_upload.pk]))
    assert report.context["training_groups"][0]["partial"] is True
    assert b"Partial legacy selection: 1 / 2 retained" in report.content
    data, group = group_payload(ready_upload, partial=True)
    url = reverse("selection", args=[ready_upload.pk])
    response = api.post(url, data)
    assert manifest(response)[0]["selected_scenario_ids"] == [first]
    ready_upload.refresh_from_db()
    assert ready_upload.selection["reject"] == [second]
    data["group"] = [group.group_id]
    response = api.post(url, data)
    assert set(manifest(response)[0]["selected_scenario_ids"]) == {first, second}
    ready_upload.refresh_from_db()
    assert ready_upload.selection["reject"] == []
    # Reposting the same rendered form remains valid after its first successful save.
    assert api.post(url, data).status_code == 200
    data.pop("group")
    response = api.post(url, data)
    assert manifest(response)[0]["selected_scenario_ids"] == [first]


@pytest.mark.parametrize(
    "kind", ["unknown", "duplicate", "member", "action", "orphan", "empty", "duplicate-member"]
)
def test_group_post_rejects_invalid_ids_without_saving(api, ready_upload, kind):
    data, group = group_payload(ready_upload)
    if kind == "unknown":
        data["group"] = ["unknown-group"]
    elif kind == "duplicate":
        data["group"] *= 2
    elif kind == "empty":
        data["group"] = []
    elif kind == "orphan":
        data[f"members_{group.group_id}"] = [ids(ready_upload)[0]]
    else:
        data[f"partial_{group.group_id}"] = "invalid" if kind == "action" else "preserve"
        data[f"members_{group.group_id}"] = ["unknown-scenario"]
        if kind == "duplicate-member":
            data[f"members_{group.group_id}"] = [ids(ready_upload)[0]] * 2
    response = api.post(reverse("selection", args=[ready_upload.pk]), data)
    assert response.status_code == 400
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


def test_group_training_navigation_and_library_use_same_all_member_groups(api, ready_upload):
    _, document = services.training_result(ready_upload.owner, ready_upload.pk)
    report = ready_upload.report
    third = deepcopy(report["scenario_document"]["scenarios"][0])
    third["scenario_id"] = "eco-opponent"
    third["opponent"]["weapon"] = "tec9"
    third["player"]["weapon"] = "awp"
    report["scenario_document"]["scenarios"].append(third)
    Upload.objects.filter(pk=ready_upload.pk).update(report=report)
    response = api.get(reverse("training", args=[ready_upload.pk]))
    assert response.context["current"].scenario_id == "eco-opponent"
    assert response.context["position"] == 1
    assert len(response.context["training_groups"]) == 2
    assert b"Group 1 / 2" in response.content
    following = response.context["following"]
    response = api.get(
        reverse("training", args=[ready_upload.pk]), {"scenario": following.scenario_id}
    )
    assert response.context["current_group"]["selected_count"] == 2
    assert b"Scenarios in this group" in response.content
    assert all(f"?scenario={sid}".encode() in response.content for sid in ids(ready_upload))
    library = api.get("/practice/").context["page"]
    assert len(library) == 2
    assert library[0]["scenario"].scenario_id == "eco-opponent"
    assert library[1]["group"]["selected_count"] == 2


def test_group_selection_requires_owner_and_csrf(api, ready_upload):
    data, _ = group_payload(ready_upload)
    url = reverse("selection", args=[ready_upload.pk])
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(ready_upload.owner)
    assert csrf_client.post(url, data).status_code == 403
    other = get_user_model().objects.create_user("other-group-user", "other-group@example.test")
    EmailAddress.objects.create(user=other, email=other.email, verified=True, primary=True)
    api.force_login(other)
    assert api.post(url, data).status_code == 404
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


def test_group_export_failure_keeps_all_submitted_members_and_never_saves(api, ready_upload):
    data, _ = group_payload(ready_upload)
    with patch("cs_map_trainer.web.services.export_scenario", side_effect=ExportError("failure")):
        response = api.post(reverse("selection", args=[ready_upload.pk]), data)
    assert response.status_code == 422
    assert response.context["selected_count"] == 2
    assert response.context["training_groups"][0]["all_selected"]
    assert response.context["training_groups"][0]["export_failed"]
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


def test_checkbox_download_saves_and_exports_same_submitted_snapshot(api, ready_upload):
    first, second = ids(ready_upload)
    services.save_training_selection(
        ready_upload.owner, ready_upload.pk, {"include": [second], "reject": [first]}
    )
    Upload.objects.filter(pk=ready_upload.pk).update(scripts=[{"console_line": "say injected"}])
    with patch("cs_map_trainer.parsing.DemoReader", side_effect=AssertionError("No parser")):
        response = api.post(
            reverse("selection", args=[ready_upload.pk]),
            checkbox_payload(ready_upload, include=[first]),
        )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "no-store" in response["Cache-Control"]
    result, files = manifest(response)
    assert result["selected_scenario_ids"] == [first]
    assert result["rejected_scenario_ids"] == []
    assert result["compatibility"] == "unverified_in_game"
    assert {"cfg/scenario-0001.cfg", "console/scenario-0001.txt", "README.txt"} <= set(files)
    ready_upload.refresh_from_db()
    assert ready_upload.selection == {"include": [first], "reject": []}
    with ZipFile(BytesIO(response.content)) as archive:
        scenario = services.training_result(ready_upload.owner, ready_upload.pk)[1].scenarios[0]
        assert archive.read("console/scenario-0001.txt").decode().strip() == (
            export_scenario(scenario).console_line
        )


def test_checkbox_practice_saves_current_values_and_keeps_historical_rejects(api, ready_upload):
    first, second = ids(ready_upload)
    services.save_training_selection(
        ready_upload.owner, ready_upload.pk, {"include": [second], "reject": [first]}
    )
    response = api.post(
        reverse("selection", args=[ready_upload.pk]),
        checkbox_payload(ready_upload, intent="practice", include=[second]),
    )
    assert response.url == reverse("training", args=[ready_upload.pk])
    ready_upload.refresh_from_db()
    assert ready_upload.selection == {"include": [second], "reject": [first]}
    response = api.post(
        reverse("selection", args=[ready_upload.pk]),
        checkbox_payload(ready_upload, intent="practice", include=[first]),
    )
    assert response.status_code == 302
    ready_upload.refresh_from_db()
    assert ready_upload.selection == {"include": [first], "reject": []}
    assert api.get(response.url).context["current"].scenario_id == first


@pytest.mark.parametrize("accept", ["text/html", "application/json"])
@pytest.mark.parametrize("include", [[], ["unknown"], ["second-scenario", "second-scenario"]])
def test_checkbox_invalid_selection_preserves_saved_and_edited_values(
    api, ready_upload, accept, include
):
    response = api.post(
        reverse("selection", args=[ready_upload.pk]),
        checkbox_payload(ready_upload, include=include),
        HTTP_ACCEPT=accept,
    )
    assert response.status_code == 400
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None
    if accept == "text/html":
        assert b'id="selection-form"' in response.content
        assert response.context["selected_count"] == len(include)
    else:
        assert response.json()["error"] == "invalid_scenario_selection"


@pytest.mark.parametrize("accept", ["text/html", "application/json"])
def test_checkbox_export_failure_does_not_save_or_skip_scenario(api, ready_upload, accept):
    with patch("cs_map_trainer.web.services.export_scenario", side_effect=ExportError("blocked")):
        response = api.post(
            reverse("selection", args=[ready_upload.pk]),
            checkbox_payload(ready_upload),
            HTTP_ACCEPT=accept,
        )
    assert response.status_code == 422
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None
    if accept == "application/json":
        assert response.json()["scenario_ids"] == ids(ready_upload)
    else:
        assert b"Cannot export a member of this group" in response.content
        assert response.context["selected_count"] == 2
    with patch("cs_map_trainer.web.services.build_pack", side_effect=ExportError("builder failed")):
        response = api.post(
            reverse("selection", args=[ready_upload.pk]), checkbox_payload(ready_upload)
        )
    assert response.status_code == 422
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


def test_checkbox_real_unsupported_scenario_is_identified_and_can_be_unchecked(api, ready_upload):
    first, second = ids(ready_upload)
    previous = {"include": [second], "reject": []}
    services.save_training_selection(ready_upload.owner, ready_upload.pk, previous)
    ready_upload.report["scenario_document"]["scenarios"][0]["player"]["view_angles"]["roll"] = 1
    ready_upload.save(update_fields=["report"])
    url = reverse("selection", args=[ready_upload.pk])
    response = api.post(url, checkbox_payload(ready_upload), HTTP_ACCEPT="application/json")
    assert response.status_code == 422
    assert response.json() == {"error": "scenario_not_exportable", "scenario_ids": [first]}
    ready_upload.refresh_from_db()
    assert ready_upload.selection == previous
    response = api.post(url, checkbox_payload(ready_upload, include=[second]))
    assert response.status_code == 200
    assert manifest(response)[0]["selected_scenario_ids"] == [second]


@pytest.mark.parametrize("verified", [False, True])
def test_checkbox_download_requires_verified_session(client, ready_upload, verified):
    if verified:
        client.force_login(ready_upload.owner)
        EmailAddress.objects.filter(user=ready_upload.owner).update(verified=False)
    response = client.post(
        reverse("selection", args=[ready_upload.pk]), checkbox_payload(ready_upload)
    )
    assert response.status_code == 302
    assert response["Content-Type"] != "application/zip"
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


def test_checkbox_download_requires_csrf(user, ready_upload):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post(
        reverse("selection", args=[ready_upload.pk]), checkbox_payload(ready_upload)
    )
    assert response.status_code == 403
    ready_upload.refresh_from_db()
    assert ready_upload.selection is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("grouped", [False, True])
def test_concurrent_tab_cannot_replace_returned_pack_snapshot(ready_upload, grouped):
    building, attempted = Event(), Event()
    first, second = ids(ready_upload)
    real_builder = services.build_pack

    def build(document, **kwargs):
        building.set()
        assert attempted.wait(10)
        return real_builder(document, **kwargs)

    def other_tab():
        try:
            assert building.wait(10)
            attempted.set()
            return services.save_training_selection(
                ready_upload.owner, ready_upload.pk, {"include": [second], "reject": []}
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        other = pool.submit(other_tab)
        with patch("cs_map_trainer.web.services.build_pack", side_effect=build):
            submitted = [first]
            if grouped:
                _, document = services.training_result(ready_upload.owner, ready_upload.pk)
                submitted = [training_groups(document)[0].group_id]
            pack = services.submit_training_selection(
                ready_upload.owner,
                ready_upload.pk,
                submitted,
                download=True,
                partial={} if grouped else None,
            )
        assert other.result(timeout=10)["selected_scenario_ids"] == [second]
    assert set(pack.manifest.selected_scenario_ids) == ({first, second} if grouped else {first})
    ready_upload.refresh_from_db()
    assert ready_upload.selection["include"] == [second]


def test_light_status_defers_result_and_preserves_full_detail_contract(api, ready_upload):
    from django.db import connection

    with CaptureQueriesContext(connection) as queries:
        response = api.get(f"/backend/uploads/{ready_upload.pk}/status/")
    assert response.json() == {"state": "ready", "error": None}
    assert "no-store" in response["Cache-Control"]
    reads = [item["sql"] for item in queries if 'FROM "trainer_upload"' in item["sql"]]
    assert len(reads) == 1
    for field in ("report", "scripts", "selection"):
        assert f'"trainer_upload"."{field}"' not in reads[0]
        assert field in api.get(f"/backend/uploads/{ready_upload.pk}/").json()


def test_light_status_owner_session_and_deletion_guards(client, api, ready_upload):
    path = f"/backend/uploads/{ready_upload.pk}/status/"
    client.logout()
    assert client.get(path).status_code == 403
    other = get_user_model().objects.create_user("other-status", "other-status@example.test")
    EmailAddress.objects.create(user=other, email=other.email, verified=False)
    client.force_login(other)
    assert client.get(path).status_code == 403
    EmailAddress.objects.filter(user=other).update(verified=True)
    assert client.get(path).status_code == 404
    client.force_login(ready_upload.owner)
    services.delete_history(ready_upload.owner, ready_upload.pk)
    assert client.get(path).status_code == 404


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
