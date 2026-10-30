import json
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from cs_map_trainer.match_statistics import MatchStatistics
from cs_map_trainer.web import services
from cs_map_trainer.web.models import BillingAccount, PlayerAnalysis, TeamMember, Upload
from cs_map_trainer.web.teams import roster_members, save_roster

pytestmark = pytest.mark.django_db
STEAM = "76561198000000001"
SECOND = "76561198000000002"


@pytest.fixture
def coach(user):
    BillingAccount.objects.create(
        owner=user,
        plan="coach",
        paid_until=timezone.now() + timedelta(days=10),
    )
    return user


@pytest.fixture
def team_upload(coach, storage, training_report):
    save_roster(
        coach,
        [
            {"steam_id": STEAM, "name": "First"},
            {"steam_id": SECOND, "name": "Second"},
        ],
    )
    upload = services.initiate(coach, uuid.uuid4(), 32, storage=storage, mode="team")
    for player in upload.player_results.all():
        report = deepcopy(training_report.model_dump(mode="json"))
        report["player_steam_id"] = player.steam_id
        for scenario in report["scenario_document"]["scenarios"]:
            scenario["player"]["steam_id"] = player.steam_id
            scenario["opponent"]["steam_id"] = "76561198000000009"
        report["groups"] = [
            {
                "group_id": "test-duel",
                "observations": 1,
                "wins": 0,
                "losses": 1,
                "win_rate": 0.0,
                "player_side": "T",
                "player_weapon": "ak47",
                "opponent_weapon": "m4a1",
                "player_cell": [0, 0, 0],
                "opponent_cell": [1, 0, 0],
                "context_limitations": [],
                "selected_scenario_ids": [
                    report["scenario_document"]["scenarios"][0]["scenario_id"]
                ],
            }
        ]
        player.status = "ready"
        player.report = report
        player.statistics = MatchStatistics(
            steam_id=player.steam_id,
            rounds_played=1,
            kills=0,
            deaths=0,
            assists=0,
            rating_assists=0,
            damage_hp=0,
            headshot_kills=0,
            adr=0.0,
            hs_percent=None,
            kpr=0.0,
            dpr=0.0,
            apr=0.0,
            kast=100.0,
            impact=-0.41,
            estimated_rating_2=0.791448,
            unavailable={"hs_percent": "no_enemy_kills"},
        ).model_dump(mode="json")
        player.save()
    upload.state = Upload.State.READY
    upload.cleanup_pending = False
    upload.save()
    return upload


@pytest.mark.parametrize("plan", ["pro", "free"])
def test_non_coach_cannot_edit_or_start_team(user, storage, plan):
    if plan == "pro":
        BillingAccount.objects.create(
            owner=user,
            plan="pro",
            paid_until=timezone.now() + timedelta(days=1),
        )
    with pytest.raises(services.IntakeError, match="coach_required"):
        save_roster(user, [{"steam_id": STEAM}])
    with pytest.raises(services.IntakeError, match="coach_required"):
        services.initiate(user, uuid.uuid4(), 32, storage=storage, mode="team")
    assert not Upload.objects.exists()
    storage.begin.assert_not_called()


@pytest.mark.parametrize(
    "players",
    [
        [],
        [{"steam_id": STEAM}] * 2,
        [{"steam_id": str(76561198000000000 + i)} for i in range(6)],
        [{"steam_id": STEAM, "name": "n" * 65}],
    ],
)
def test_roster_validation_is_atomic(coach, players):
    save_roster(coach, [{"steam_id": STEAM, "name": "Original"}])
    with pytest.raises(services.IntakeError, match="invalid_team_roster"):
        save_roster(coach, players)
    assert list(roster_members(coach).values_list("name", flat=True)) == ["Original"]


def test_five_players_and_database_position_limit(coach):
    members = save_roster(coach, [{"steam_id": str(76561198000000000 + i)} for i in range(5)])
    assert len(members) == 5
    with pytest.raises(IntegrityError), transaction.atomic():
        TeamMember.objects.create(team=members[0].team, steam_id=SECOND, position=5)


def test_snapshot_and_retry_survive_edit_and_expiry(coach, storage):
    save_roster(coach, [{"steam_id": STEAM, "name": "Original"}])
    request_id = uuid.uuid4()
    upload = services.initiate(coach, request_id, 32, storage=storage, mode="team")
    save_roster(coach, [{"steam_id": SECOND, "name": "Replacement"}])
    BillingAccount.objects.filter(owner=coach).update(paid_until=timezone.now())
    retried = services.initiate(coach, request_id, 32, storage=storage, mode="team")
    assert retried.pk == upload.pk
    assert list(upload.player_results.values_list("steam_id", "name")) == [(STEAM, "Original")]
    assert storage.begin.call_count == 1
    with pytest.raises(services.IntakeError, match="idempotency_conflict"):
        services.initiate(coach, request_id, 32, STEAM, storage)


def test_team_intake_api_uses_server_roster(api, coach, storage):
    save_roster(coach, [{"steam_id": STEAM}])
    with patch("cs_map_trainer.web.views.R2", return_value=storage):
        response = api.post(
            "/backend/uploads/",
            {
                "mode": "team",
                "request_id": str(uuid.uuid4()),
                "size_bytes": 32,
                "has_upload_rights": True,
            },
            content_type="application/json",
        )
    assert response.status_code == 201
    assert response.json()["players"][0]["steam_id"] == STEAM
    assert response.json()["mode"] == "team"


def test_team_requires_explicit_player_and_isolates_selection(api, team_upload):
    base = f"/backend/uploads/{team_upload.pk}/"
    assert api.get(base + "selection/").json()["error"] == "player_required"
    first = team_upload.player_results.get(steam_id=STEAM)
    scenario_id = first.report["scenario_document"]["scenarios"][0]["scenario_id"]
    response = api.post(
        base + f"players/{STEAM}/selection/",
        {
            "include": [scenario_id],
            "reject": [],
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    first.refresh_from_db()
    assert first.selection["include"] == [scenario_id]
    assert team_upload.player_results.get(steam_id=SECOND).selection is None
    assert api.get(base + "players/76561198000000009/selection/").status_code == 404


def test_team_reports_practice_and_exports_survive_downgrade(api, coach, team_upload):
    BillingAccount.objects.filter(owner=coach).update(paid_until=timezone.now())
    overview = api.get(f"/uploads/{team_upload.pk}/")
    assert overview.status_code == 200
    assert b"First" in overview.content and b"Second" in overview.content
    assert b"0.79" in overview.content
    report = api.get(f"/uploads/{team_upload.pk}/players/{STEAM}/")
    assert report.status_code == 200
    assert f"/players/{STEAM}/selection/" in report.content.decode()
    library = api.get("/practice/")
    assert library.context["choose_player"]
    library = api.get(f"/practice/?player={STEAM}")
    assert all(entry["steam_id"] == STEAM for entry in library.context["page"])
    player = team_upload.player_results.get(steam_id=STEAM)
    scenario_id = player.report["scenario_document"]["scenarios"][0]["scenario_id"]
    training = api.get(f"/uploads/{team_upload.pk}/players/{STEAM}/training/")
    assert training.status_code == 200
    exported = api.get(
        f"/backend/uploads/{team_upload.pk}/players/{STEAM}/scenarios/{scenario_id}/export/"
    )
    assert exported.status_code == 200


def test_team_results_are_private(api, team_upload):
    other = get_user_model().objects.create_user("other", "other@example.test", "some-password")
    Upload.objects.filter(pk=team_upload.pk).update(owner=other)
    assert api.get(f"/uploads/{team_upload.pk}/").status_code == 404
    assert (
        api.get(f"/backend/uploads/{team_upload.pk}/players/{STEAM}/selection/").status_code == 404
    )


def test_missing_player_is_explicit_and_delete_cleans_all(api, team_upload):
    PlayerAnalysis.objects.filter(upload=team_upload, steam_id=SECOND).update(
        status="missing",
        report=None,
    )
    assert api.get(f"/uploads/{team_upload.pk}/players/{SECOND}/").status_code == 409
    services.delete_history(team_upload.owner, team_upload.pk)
    assert not team_upload.player_results.exists()
    assert api.get(f"/uploads/{team_upload.pk}/").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_roster_edits_replace_one_whole_snapshot(coach):
    choices = [
        [{"steam_id": str(76561198000000000 + offset + i)} for i in range(5)] for offset in (0, 10)
    ]

    def update(players):
        close_old_connections()
        try:
            save_roster(coach, players)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, players) for players in choices]
        for future in futures:
            future.result(timeout=30)
    saved = set(roster_members(coach).values_list("steam_id", flat=True))
    assert saved in [{player["steam_id"] for player in players} for players in choices]


def test_review_scope_and_account_deletion_clear_player_snapshots(api, team_upload):
    from cs_map_trainer.web.practice import review_scenario

    for steam_id in (STEAM, SECOND):
        result = team_upload.player_results.get(steam_id=steam_id)
        scenario_id = result.report["scenario_document"]["scenarios"][0]["scenario_id"]
        review_scenario(
            team_upload.owner,
            team_upload.pk,
            scenario_id,
            "easy",
            steam_id=steam_id,
        )
    assert team_upload.practice_reviews.count() == 2
    result_ids = list(team_upload.player_results.values_list("pk", flat=True))
    team_upload.owner.delete()
    assert not PlayerAnalysis.objects.filter(pk__in=result_ids).exists()
    assert not team_upload.practice_reviews.exists()


def test_native_team_worker_persists_five_players_and_deletes_input(
    coach,
    storage,
    settings,
    tmp_path,
    api,
):
    from cs_map_trainer.analysis import roster
    from cs_map_trainer.parsing import DemoReader
    from cs_map_trainer.web import tasks

    demo = os.environ.get("CS_MAP_TRAINER_DEMO")
    if not demo:
        pytest.skip("Set CS_MAP_TRAINER_DEMO to an authorized local CS2 demo")
    players = roster(DemoReader(Path(demo))).players[:5]
    assert len(players) == 5
    save_roster(
        coach,
        [
            {"steam_id": player.steam_id, "name": f"Player {index}"}
            for index, player in enumerate(players, start=1)
        ],
    )
    settings.WORK_ROOT = tmp_path / "work"
    storage.download.side_effect = lambda upload, path: shutil.copyfile(demo, path)
    upload = services.initiate(
        coach, uuid.uuid4(), Path(demo).stat().st_size, storage=storage, mode="team"
    )
    Upload.objects.filter(pk=upload.pk).update(state=Upload.State.QUEUED)
    with patch.object(tasks, "R2", return_value=storage):
        tasks.process_upload(upload.pk)
    upload.refresh_from_db()
    assert upload.state == Upload.State.READY, upload.error_code
    assert upload.report is None
    assert not upload.cleanup_pending
    assert not (settings.WORK_ROOT / str(upload.pk)).exists()
    assert upload.player_results.count() == 5
    for result in upload.player_results.all():
        assert result.status == "ready"
        assert result.report["player_steam_id"] == result.steam_id
        assert result.statistics["steam_id"] == result.steam_id
        assert result.statistics["estimated_rating_2"] is not None
        assert len(result.scripts) <= 10
    overview = api.get(f"/uploads/{upload.pk}/")
    assert overview.status_code == 200
    assert b"Estimated Rating 2.0" in overview.content
    assert b"Not present in this demo" not in overview.content
    storage.delete.assert_called_once()


def parser_payload(upload):
    return {
        "players": [
            {
                "steam_id": result.steam_id,
                "status": result.status,
                "report": result.report,
                "statistics": result.statistics,
            }
            for result in upload.player_results.all()
        ],
        "error": None,
    }


def test_team_parser_json_boundary_generates_commands(team_upload, tmp_path):
    from cs_map_trainer.web import tasks

    payload = parser_payload(team_upload)

    def child(command, env, **kwargs):
        assert json.loads(command[-2]) == [STEAM, SECOND]
        Path(command[-1]).write_text(json.dumps(payload))

    with patch.object(tasks, "run_bounded", side_effect=child):
        result, scripts = tasks.run_parser(team_upload, tmp_path)
    assert scripts is None
    tasks.persist_results(team_upload, result, scripts)
    for player in team_upload.player_results.all():
        assert player.scripts[0]["console_line"]
        assert player.statistics["steam_id"] == player.steam_id


@pytest.mark.parametrize("kind", ["roster", "statistics", "scenario"])
def test_team_parser_rejects_mixed_player_payloads(team_upload, kind):
    from cs_map_trainer.web import tasks

    payload = parser_payload(team_upload)
    if kind == "roster":
        payload["players"].reverse()
    elif kind == "statistics":
        payload["players"][0]["statistics"]["steam_id"] = SECOND
    else:
        payload["players"][0]["report"]["scenario_document"]["scenarios"][0]["player"][
            "steam_id"
        ] = SECOND
    with pytest.raises(ValueError):
        tasks.validate_team_result(team_upload, payload)


def test_worker_rolls_back_all_players_after_invalid_result(
    team_upload, storage, settings, tmp_path
):
    from cs_map_trainer.web import tasks

    payload = parser_payload(team_upload)
    payload["players"][1]["statistics"]["steam_id"] = STEAM
    Upload.objects.filter(pk=team_upload.pk).update(state=Upload.State.QUEUED)
    team_upload.player_results.update(status="pending", report=None, statistics=None)
    settings.WORK_ROOT = tmp_path / "work"
    with (
        patch.object(tasks, "R2", return_value=storage),
        patch.object(
            tasks,
            "run_parser",
            return_value=(payload, None),
        ),
    ):
        tasks.process_upload(team_upload.pk)
    team_upload.refresh_from_db()
    assert team_upload.state == Upload.State.FAILED
    assert not team_upload.quota_charged
    assert not team_upload.player_results.exclude(report=None, statistics=None).exists()
    assert not team_upload.cleanup_pending
