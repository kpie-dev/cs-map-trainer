from copy import deepcopy
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from test_analysis import OPPONENT, PLAYER, THIRD, FakeReader

from cs_map_trainer.analysis import analyze
from cs_map_trainer.parsing import DemoError
from cs_map_trainer.team_analysis import (
    TeamAnalysisRequest,
    TeamAnalysisResult,
    analyze_team,
)

pytest_plugins = ["test_analysis"]


def test_shared_extraction_preserves_single_player_report(reader):
    expected = analyze(lambda: deepcopy(reader), str(PLAYER))
    for name in ("players", "combat", "snapshots", "locations"):
        setattr(reader, name, Mock(wraps=getattr(reader, name)))
    result = analyze_team(reader, [str(PLAYER), str(OPPONENT), str(THIRD)])
    assert [player.status for player in result.players] == ["ready", "ready", "missing"]
    actual = result.players[0].report
    assert actual.model_dump(exclude={"metrics"}) == expected.model_dump(exclude={"metrics"})
    assert result.players[1].report.eligible_wins == 1
    assert result.players[2].report is None and result.players[2].statistics is None
    reader.players.assert_called_once()
    reader.combat.assert_called_once()
    reader.snapshots.assert_called_once_with([10, 99])
    reader.locations.assert_called_once_with([99])
    TeamAnalysisResult.model_validate_json(result.model_dump_json())


def test_none_present_returns_explicit_team_error_without_combat():
    reader = FakeReader()
    reader.combat = Mock(side_effect=AssertionError("should not parse combat"))
    result = analyze_team(reader, [str(THIRD)])
    assert result.error == "team_players_not_in_demo"
    assert result.players[0].status == "missing"


@pytest.mark.parametrize(
    "ids", [[], [str(PLAYER)] * 2, ["a" * 17], [str(PLAYER + index) for index in range(6)]]
)
def test_invalid_roster_rejected_before_parser(ids):
    with pytest.raises(ValidationError):
        TeamAnalysisRequest(steam_ids=ids)


def test_parser_failure_is_not_missing_player_partial_success(reader):
    reader.snapshots = Mock(side_effect=DemoError("native failure"))
    with pytest.raises(DemoError, match="native failure"):
        analyze_team(reader, [str(PLAYER), str(THIRD)])


def test_maximum_scenarios_is_per_player(reader):
    original = deepcopy(reader.kill_rows[0])
    original_damage = deepcopy(reader.damage_rows[0])
    original_snapshots = deepcopy(reader.snapshot_rows)
    reader.round_rows[0]["end_tick"] = 20000
    reader.kill_rows = []
    reader.damage_rows = []
    reader.snapshot_rows = []
    for index in range(24):
        offset = 500 * index
        event = {**original, "tick": 120 + offset}
        if index % 2:
            event.update(
                attacker_steamid=PLAYER,
                victim_steamid=OPPONENT,
                attacker_side=original["victim_side"],
                victim_side=original["attacker_side"],
            )
        reader.kill_rows.append(event)
        reader.damage_rows.append({**original_damage, "tick": 100 + offset})
        reader.snapshot_rows.extend(
            {**snapshot, "tick": 99 + offset} for snapshot in original_snapshots
        )
    result = analyze_team(reader, [str(PLAYER), str(OPPONENT)])
    for player in result.players:
        report = player.report
        assert report.eligible_candidates == 12
        assert len(report.scenario_document.scenarios) == 10
        assert report.omitted_by_limit == 2
    assert len(reader.requested_ticks) == len(reader.requested_location_ticks) == 1


def test_result_contract_rejects_mixed_ids_missing_payloads_and_wrong_error(reader):
    payload = analyze_team(reader, [str(PLAYER)]).model_dump(mode="json")
    for mutate in (
        lambda value: value.update(error="team_players_not_in_demo"),
        lambda value: value["players"][0].update(status="missing"),
        lambda value: value["players"][0].update(steam_id=str(OPPONENT)),
        lambda value: value["players"].append(deepcopy(value["players"][0])),
    ):
        invalid = deepcopy(payload)
        mutate(invalid)
        with pytest.raises(ValidationError):
            TeamAnalysisResult.model_validate(invalid)
