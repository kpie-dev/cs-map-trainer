import uuid
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client

from cs_map_trainer.web import services, tasks
from cs_map_trainer.web.models import AccountPreferences, Upload

pytestmark = pytest.mark.django_db
STEAM = "76561198000000001"
OTHER_STEAM = "76561198000000009"


@pytest.mark.parametrize(
    "steam_id",
    [
        None,
        "",
        76561198000000001,
        True,
        [],
        {},
        "STEAM_0:1:123",
        "https://steamcommunity.com/id/example",
        "123",
        "7" * 18,
        "７" * 17,
        "7" * 16 + "x",
    ],
)
def test_invalid_id_has_no_side_effects(api, storage, steam_id):
    with patch("cs_map_trainer.web.views.R2", return_value=storage) as factory:
        response = api.post(
            "/backend/uploads/",
            {
                "request_id": str(uuid.uuid4()),
                "size_bytes": 32,
                "has_upload_rights": True,
                "player_steam_id": steam_id,
            },
            content_type="application/json",
        )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_player_steam_id"}
    factory.assert_not_called()
    assert not Upload.objects.exists()
    assert not AccountPreferences.objects.exists()


def test_missing_id_is_not_replaced_by_last_suggestion(api, user, storage):
    AccountPreferences.objects.create(owner=user, last_player_steam_id=STEAM)
    with patch("cs_map_trainer.web.views.R2", return_value=storage) as factory:
        response = api.post(
            "/backend/uploads/",
            {"request_id": str(uuid.uuid4()), "size_bytes": 32, "has_upload_rights": True},
            content_type="application/json",
        )
    assert response.status_code == 400
    factory.assert_not_called()
    assert not Upload.objects.exists()


def test_suggestion_is_normalized_and_reused_on_another_device(user, storage):
    upload = services.initiate(user, uuid.uuid4(), 32, f" \n{STEAM}\t ", storage)
    assert upload.player_steam_id == STEAM
    client = Client()
    client.force_login(user)
    text = client.get("/").content.decode()
    assert f'value="{STEAM}"' in text
    assert client.get("/backend/history/").json()["last_player_steam_id"] == STEAM
    assert STEAM in client.get("/account/").content.decode()


def test_idempotent_retry_does_not_change_player_or_suggestion(user, storage):
    request_id = uuid.uuid4()
    original = services.initiate(user, request_id, 32, STEAM, storage)
    with pytest.raises(services.IntakeError, match="idempotency_conflict"):
        services.initiate(user, request_id, 32, OTHER_STEAM, storage)
    Upload.objects.filter(pk=original.pk).update(state="ready", cleanup_pending=False)
    services.initiate(user, uuid.uuid4(), 32, OTHER_STEAM, storage)
    assert services.initiate(user, request_id, 32, STEAM, storage).pk == original.pk
    assert AccountPreferences.objects.get(owner=user).last_player_steam_id == OTHER_STEAM
    assert storage.begin.call_count == 2
    original.refresh_from_db()
    assert original.player_steam_id == STEAM


def test_storage_failure_does_not_persist_suggestion_or_quota(user, storage):
    storage.begin.side_effect = TimeoutError("test storage unavailable")
    with pytest.raises(TimeoutError):
        services.initiate(user, uuid.uuid4(), 32, STEAM, storage)
    assert not AccountPreferences.objects.exists()
    assert not Upload.objects.exists()
    assert services.quota_used(user) == 0


def test_changing_player_does_not_bypass_active_or_monthly_limit(user, storage):
    for steam_id in [STEAM, OTHER_STEAM, STEAM]:
        upload = services.initiate(user, uuid.uuid4(), 32, steam_id, storage)
        with pytest.raises(services.IntakeError, match="active_upload_exists"):
            services.initiate(user, uuid.uuid4(), 32, OTHER_STEAM, storage)
        Upload.objects.filter(pk=upload.pk).update(state="ready", cleanup_pending=False)
    with pytest.raises(services.IntakeError, match="monthly_demo_limit"):
        services.initiate(user, uuid.uuid4(), 32, OTHER_STEAM, storage)
    assert services.quota_used(user) == 3


def test_two_accounts_can_analyze_same_player_without_sharing_results(user, storage, api):
    other = get_user_model().objects.create_user("other", "other@example.test")
    EmailAddress.objects.create(user=other, email=other.email, verified=True)
    request_id = uuid.uuid4()
    own = services.initiate(user, request_id, 32, STEAM, storage)
    foreign = services.initiate(other, request_id, 32, STEAM, storage)
    assert own.pk != foreign.pk
    assert services.quota_used(user) == services.quota_used(other) == 1
    assert api.get(f"/backend/uploads/{foreign.pk}/").status_code == 404
    assert api.get(f"/uploads/{foreign.pk}/").status_code == 404
    assert api.get(f"/backend/uploads/{foreign.pk}/pack/").status_code == 404
    assert api.get(f"/backend/uploads/{foreign.pk}/selection/").status_code == 404
    assert api.get("/backend/history/").json()["uploads"][0]["id"] == str(own.pk)
    api.force_login(other)
    assert api.get(f"/backend/uploads/{own.pk}/").status_code == 404


def test_suggestions_do_not_leak_between_accounts(user, storage, api):
    services.initiate(user, uuid.uuid4(), 32, STEAM, storage)
    other = get_user_model().objects.create_user("other", "other@example.test")
    EmailAddress.objects.create(user=other, email=other.email, verified=True)
    api.force_login(other)
    assert api.get("/backend/history/").json()["last_player_steam_id"] == ""
    assert STEAM not in api.get("/account/").content.decode()


def test_parser_and_report_use_upload_player_not_last_suggestion(upload, user, tmp_path):
    AccountPreferences.objects.filter(owner=user).update(last_player_steam_id=OTHER_STEAM)
    (tmp_path / "result.json").write_text('{"error": "linked_player_not_in_demo"}')
    with patch.object(tasks, "run_bounded") as run:
        with pytest.raises(tasks.DemoRejected, match="linked_player_not_in_demo"):
            tasks.run_parser(upload, tmp_path)
    assert run.call_args.args[0][-2] == STEAM


def test_home_guide_is_a_closed_dialog_opened_by_a_button(api):
    response = api.get("/")
    text = response.content.decode()
    assert '<dialog id="steam-id-guide"' in text
    assert " open" not in text.split('<dialog id="steam-id-guide"', 1)[1].split(">", 1)[0]
    assert 'id="steam-id-guide-open" type="button"' in text
    assert 'commandfor="steam-id-guide" command="show-modal"' in text
    assert 'href="#steam-id-guide"' not in text
    assert 'method="dialog"' in text
    assert "Account details" in text
    assert "Steam ID" in text
    assert "not screenshots" in text
    assert 'pattern="[0-9]{17}"' in text
    assert "steam-account-menu.svg" in text
    assert "steam-account-id.svg" in text
    assert "OpenID" not in text


def test_anonymous_home_keeps_guide_in_a_closed_dialog(client):
    text = client.get("/").content.decode()
    assert '<dialog id="steam-id-guide"' in text
    assert " open" not in text.split('<dialog id="steam-id-guide"', 1)[1].split(">", 1)[0]
    assert '<section id="steam-id-guide"' not in text
