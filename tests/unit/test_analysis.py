import json
from copy import deepcopy
from dataclasses import dataclass, field

import polars as pl
import pytest
from pydantic import ValidationError

from cs_map_trainer.analysis import AnalysisReport, analyze, roster
from cs_map_trainer.parsing import DemoError
from cs_map_trainer.scenarios import MapIdentity, ScenarioDocument

PLAYER = 76561198000000001
OPPONENT = 76561198000000002
THIRD = 76561198000000003


@dataclass
class FakeReader:
    map: MapIdentity = field(
        default_factory=lambda: MapIdentity(
            name="de_mirage", game_build=1, revision="test-unverified"
        )
    )
    sha256: str = "0" * 64
    size_bytes: int = 100
    round_rows: list = field(
        default_factory=lambda: [
            {
                "round_num": 1,
                "start_tick": 0,
                "freeze_end_tick": 10,
                "end_tick": 500,
                "is_knife_round": False,
            }
        ]
    )
    kill_rows: list = field(default_factory=list)
    damage_rows: list = field(default_factory=list)
    snapshot_rows: list = field(default_factory=list)
    location_rows: list = field(default_factory=list)
    requested_ticks: list = field(default_factory=list)
    requested_location_ticks: list = field(default_factory=list)

    def players(self):
        return pl.DataFrame(
            [
                {"steamid": PLAYER, "name": "Synthetic player", "side": "terrorist"},
                {"steamid": OPPONENT, "name": None, "side": "counter-terrorist"},
                {"steamid": 0, "name": "Bot", "side": "counter-terrorist"},
            ]
        )

    def combat(self):
        return tuple(
            pl.DataFrame(rows) for rows in (self.round_rows, self.kill_rows, self.damage_rows)
        )

    def snapshots(self, ticks):
        self.requested_ticks.append(ticks)
        return pl.DataFrame(self.snapshot_rows)

    def locations(self, ticks):
        self.requested_location_ticks.append(ticks)
        return pl.DataFrame(self.location_rows)


@pytest.fixture(params=["de_mirage", "de_dust2"])
def reader(request):
    reader = FakeReader()
    reader.map = reader.map.model_copy(update={"name": request.param})
    reader.kill_rows = [
        {
            "tick": 120,
            "attacker_steamid": OPPONENT,
            "victim_steamid": PLAYER,
            "attacker_side": "counter-terrorist",
            "victim_side": "terrorist",
            "weapon": "m4a1",
            "penetrated": 0,
            "thrusmoke": False,
        }
    ]
    reader.damage_rows = [
        {
            "tick": tick,
            "attacker_steamid": OPPONENT,
            "victim_steamid": PLAYER,
            "weapon": "m4a1",
        }
        for tick in (100, 120)
    ]
    reader.snapshot_rows = [
        {
            "tick": 99,
            "steamid": steamid,
            "side": side,
            "x": x,
            "y": 2.0,
            "z": 3.0,
            "pitch": 2.0,
            "yaw": 270.0,
            "health": 100,
            "active_weapon": weapon,
            "is_crouched": False,
            "is_jumping": False,
            "is_blinded": False,
        }
        for steamid, side, weapon, x in (
            (PLAYER, "terrorist", "ak47", 1.0),
            (OPPONENT, "counter-terrorist", "m4a1", 100.0),
        )
    ]
    reader.location_rows = [
        {"tick": 99, "steamid": PLAYER, "last_place_name": "BombsiteA"},
        {"tick": 99, "steamid": OPPONENT, "last_place_name": "CTSpawn"},
    ]
    return reader


def run(reader, **kwargs):
    return analyze(lambda: reader, str(PLAYER), **kwargs)


def test_analysis_report_can_be_exported_without_reparsing(reader):
    from cs_map_trainer.packs import build_pack, load_scenarios

    report = run(reader)
    assert report.scenario_document is not None
    requested_ticks = list(reader.requested_ticks)
    document = load_scenarios(report.model_dump_json().encode())
    pack = build_pack(document, include_cfg=True)
    assert pack.manifest.selected_scenario_ids == [
        scenario.scenario_id for scenario in report.scenario_document.scenarios
    ]
    assert pack.manifest.entries[0].source.rules_version == "damage-window-v3"
    assert pack.manifest.compatibility == "unverified_in_game"
    assert report.map == reader.map
    assert all(entry.map == reader.map for entry in pack.manifest.entries)
    assert reader.requested_ticks == requested_ticks


def test_native_locations_are_saved_for_the_exact_scenario_snapshot(reader):
    reader.location_rows.extend(
        [
            {"tick": 98, "steamid": PLAYER, "last_place_name": "WrongPreviousTick"},
            {"tick": 120, "steamid": PLAYER, "last_place_name": "WrongDeathTick"},
            {"tick": 99, "steamid": THIRD, "last_place_name": "WrongPlayer"},
        ]
    )
    report = run(reader)
    scenario = report.scenario_document.scenarios[0]
    assert report.analysis_version == 3
    assert reader.requested_location_ticks == [[99]]
    assert report.scenario_locations[scenario.scenario_id].model_dump() == {
        "snapshot_tick": 99,
        "source": "m_szLastPlaceName",
        "player": "BombsiteA",
        "opponent": "CTSpawn",
    }
    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored.scenario_locations == report.scenario_locations
    assert restored.scenario_document == report.scenario_document


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_native_name_is_explicit_and_does_not_exclude_a_duel(reader, value, caplog):
    reader.location_rows[0]["last_place_name"] = value
    report = run(reader)
    scenario = report.scenario_document.scenarios[0]
    locations = report.scenario_locations[scenario.scenario_id]
    assert locations.player is None
    assert locations.opponent == "CTSpawn"
    assert report.eligible_candidates == 1
    assert not report.excluded
    assert "Native demo location unavailable for 1 of 2" in caplog.text


def test_location_rows_are_not_carried_forward_from_other_ticks(reader, caplog):
    for row in reader.location_rows:
        row["tick"] = 98
    report = run(reader)
    locations = next(iter(report.scenario_locations.values()))
    assert locations.player is locations.opponent is None
    assert "Native demo location unavailable for 2 of 2" in caplog.text


def test_native_names_are_trimmed_but_not_replaced_in_the_report(reader):
    reader.location_rows[0]["last_place_name"] = "  BombsiteA  "
    assert next(iter(run(reader).scenario_locations.values())).player == "BombsiteA"


def test_duplicate_native_location_identity_fails_explicitly(reader):
    reader.location_rows.append(deepcopy(reader.location_rows[0]))
    with pytest.raises(DemoError, match="Ambiguous duplicate player location"):
        run(reader)


def test_legacy_v2_report_remains_readable_without_location_metadata(reader):
    payload = json.loads(run(reader).model_dump_json())
    payload["analysis_version"] = 2
    payload.pop("scenario_locations")
    report = AnalysisReport.model_validate_json(json.dumps(payload))
    assert report.analysis_version == 2
    assert report.scenario_locations == {}
    from cs_map_trainer.packs import load_scenarios

    assert load_scenarios(json.dumps(payload).encode()) == report.scenario_document


@pytest.mark.parametrize("corruption", ["tick", "scenario", "version", "source"])
def test_location_metadata_cannot_claim_a_different_tick_scenario_or_source(reader, corruption):
    payload = json.loads(run(reader).model_dump_json())
    scenario_id = next(iter(payload["scenario_locations"]))
    if corruption == "tick":
        payload["scenario_locations"][scenario_id]["snapshot_tick"] = 120
    elif corruption == "scenario":
        payload["scenario_locations"]["other"] = payload["scenario_locations"].pop(scenario_id)
    elif corruption == "source":
        payload["scenario_locations"][scenario_id]["source"] = "guessed_xyz"
    else:
        payload["analysis_version"] = 2
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate_json(json.dumps(payload))


def test_negative_coordinates_and_height_cells_preserve_map(reader):
    reader.snapshot_rows[0].update(x=-257.0, y=-1.0, z=513.0)
    reader.snapshot_rows[1].update(x=-512.0, y=256.0, z=-1.0)
    report = run(reader)
    scenario = report.scenario_document.scenarios[0]
    assert report.map == scenario.map == reader.map
    assert scenario.player.position.model_dump() == {"x": -257.0, "y": -1.0, "z": 513.0}
    assert report.groups[0].player_cell == (-2, -1, 2)
    assert report.groups[0].opponent_cell == (-2, 1, -1)


def test_shared_snapshot_precedes_first_damage_and_preserves_aim(reader):
    result = run(reader)
    assert result.status == "candidates_ready"
    assert reader.requested_ticks == [[99]]
    scenario = result.scenario_document.scenarios[0]
    assert scenario.source.snapshot_tick == 99
    assert scenario.source.contact_tick == 100
    assert scenario.source.death_tick == 120
    assert scenario.player.position.x == 1
    assert scenario.opponent.position.x == 100
    assert scenario.player.view_angles.yaw == -90
    assert scenario.player.view_angles.pitch == 2
    assert scenario.opponent.view_angles.yaw == -90
    assert scenario.opponent.view_angles.pitch == 2
    assert "opponent_aim_inferred_toward_player" not in scenario.limitations
    assert "map_geometry_unverified" in scenario.limitations
    assert result.deaths_considered == result.eligible_candidates == 1
    assert result.metrics.input_bytes == 100
    assert result.metrics.cpu_seconds >= 0
    ScenarioDocument.model_validate_json(result.scenario_document.model_dump_json())


@pytest.mark.parametrize(
    ("missing", "pitch", "yaw"),
    [
        (("pitch",), -45.0, -90.0),
        (("yaw",), 2.0, 45.0),
        (("pitch", "yaw"), -45.0, 45.0),
    ],
)
@pytest.mark.parametrize("omit_fields", [False, True])
def test_missing_opponent_angles_aim_toward_player(reader, missing, pitch, yaw, omit_fields):
    reader.snapshot_rows[0].update(x=10.0, y=10.0, z=20.0)
    reader.snapshot_rows[1].update(x=0.0, y=0.0, z=20.0 - 200**0.5)
    for angle in missing:
        if omit_fields:
            reader.snapshot_rows[1].pop(angle)
        else:
            reader.snapshot_rows[1][angle] = None
    result = run(reader)
    scenario = result.scenario_document.scenarios[0]
    assert scenario.opponent.view_angles.pitch == pytest.approx(pitch)
    assert scenario.opponent.view_angles.yaw == pytest.approx(yaw)
    assert scenario.player.view_angles.pitch == 2
    assert scenario.player.view_angles.yaw == -90
    assert "opponent_aim_inferred_toward_player" in scenario.limitations
    assert "opponent_aim_inferred_toward_player" in result.groups[0].context_limitations
    assert result.rules_version == scenario.source.rules_version == "damage-window-v3"
    ScenarioDocument.model_validate_json(result.scenario_document.model_dump_json())


@pytest.mark.parametrize(
    ("target", "pitch", "yaw"),
    [
        ((10.0, 0.0, 0.0), 0.0, 0.0),
        ((0.0, 10.0, 0.0), 0.0, 90.0),
        ((-10.0, 0.0, 0.0), 0.0, -180.0),
        ((0.0, -10.0, 0.0), 0.0, -90.0),
        ((10.0, 0.0, -10.0), 45.0, 0.0),
    ],
)
def test_inferred_opponent_angles_follow_source_coordinates(reader, target, pitch, yaw):
    reader.snapshot_rows[0].update(zip(("x", "y", "z"), target, strict=True))
    reader.snapshot_rows[1].update(x=0.0, y=0.0, z=0.0, pitch=None, yaw=None)
    angles = run(reader).scenario_document.scenarios[0].opponent.view_angles
    assert angles.pitch == pytest.approx(pitch)
    assert angles.yaw == pytest.approx(yaw)


@pytest.mark.parametrize("angle", ["pitch", "yaw"])
def test_missing_player_angles_are_not_inferred(reader, angle):
    reader.snapshot_rows[0][angle] = None
    assert run(reader).excluded[0].reason == "missing_snapshot_position_or_angles"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("x", None, "missing_snapshot_position_or_angles"),
        ("x", float("inf"), "invalid_snapshot_values"),
        ("pitch", 100.0, "invalid_snapshot_values"),
        ("pitch", float("nan"), "invalid_snapshot_values"),
        ("yaw", float("inf"), "invalid_snapshot_values"),
    ],
)
def test_opponent_aim_fallback_does_not_hide_invalid_data(reader, field, value, reason):
    reader.snapshot_rows[1].update(pitch=None, yaw=None)
    reader.snapshot_rows[1][field] = value
    assert run(reader).excluded[0].reason == reason


@pytest.mark.parametrize("height", [0.0, 10.0])
def test_missing_opponent_yaw_requires_a_defined_horizontal_direction(reader, height):
    reader.snapshot_rows[1].update(reader.snapshot_rows[0])
    reader.snapshot_rows[1].update(
        steamid=OPPONENT, side="counter-terrorist", pitch=None, yaw=None, z=3.0 + height
    )
    assert run(reader).excluded[0].reason == "undefined_opponent_aim_direction"


def test_vertical_pitch_fallback_preserves_recorded_yaw(reader):
    reader.snapshot_rows[1].update(x=1.0, y=2.0, z=-7.0, pitch=None)
    angles = run(reader).scenario_document.scenarios[0].opponent.view_angles
    assert angles.pitch == -90.0
    assert angles.yaw == -90.0


def test_contact_includes_damage_dealt_by_the_selected_player(reader):
    reader.damage_rows.insert(
        0,
        {
            "tick": 95,
            "attacker_steamid": PLAYER,
            "victim_steamid": OPPONENT,
            "weapon": "ak47",
        },
    )
    for row in reader.snapshot_rows:
        row["tick"] = 94
    assert run(reader).scenario_document.scenarios[0].source.contact_tick == 95


def test_single_hit_death_uses_previous_tick(reader):
    reader.damage_rows = reader.damage_rows[1:]
    for row in reader.snapshot_rows:
        row["tick"] = 119
    scenario = run(reader).scenario_document.scenarios[0]
    assert scenario.source.contact_tick == scenario.source.death_tick
    assert scenario.source.snapshot_tick == 119


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("attacker_steamid", None, "world_or_suicide"),
        ("attacker_steamid", PLAYER, "world_or_suicide"),
        ("attacker_side", "terrorist", "teamkill"),
        ("attacker_side", None, "unknown_side"),
        ("weapon", "hegrenade", "unsupported_killing_weapon"),
        ("weapon", "knife", "unsupported_killing_weapon"),
        ("weapon", "world", "unsupported_killing_weapon"),
        ("penetrated", 1, "penetration"),
        ("thrusmoke", True, "through_smoke"),
        ("tick", 5, "outside_live_round"),
        ("tick", 501, "outside_live_round"),
    ],
)
def test_excludes_unsupported_deaths_before_snapshot_decoding(reader, field, value, reason):
    reader.kill_rows[0][field] = value
    result = run(reader)
    assert [item.reason for item in result.excluded] == [reason]
    assert result.scenario_document is None
    assert reader.requested_ticks == []


def test_skips_knife_round(reader):
    reader.round_rows[0]["is_knife_round"] = True
    assert run(reader).excluded[0].reason == "knife_round"


def test_missing_damage_is_not_replaced_with_death_position(reader):
    reader.damage_rows = []
    assert run(reader).excluded[0].reason == "missing_damage_contact"


def test_damage_before_round_freeze_end_is_not_contact(reader):
    reader.damage_rows[0]["tick"] = 5
    reader.damage_rows[1]["tick"] = 5
    assert run(reader).excluded[0].reason == "missing_damage_contact"


def test_requires_a_pre_contact_live_tick(reader):
    for row in reader.damage_rows:
        row["tick"] = 10
    assert run(reader).excluded[0].reason == "no_pre_contact_live_tick"


def test_excludes_multi_party_damage(reader):
    reader.damage_rows.append(
        {"tick": 105, "attacker_steamid": THIRD, "victim_steamid": PLAYER, "weapon": "ak47"}
    )
    assert run(reader).excluded[0].reason == "multi_party_damage"


def test_requires_both_players_at_the_exact_tick(reader):
    reader.snapshot_rows[1]["tick"] = 98
    assert run(reader).excluded[0].reason == "missing_shared_snapshot"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("health", 0, "missing_or_dead_snapshot_participant"),
        ("health", None, "missing_or_dead_snapshot_participant"),
        ("x", None, "missing_snapshot_position_or_angles"),
        ("x", float("inf"), "invalid_snapshot_values"),
        ("pitch", 100.0, "invalid_snapshot_values"),
        ("active_weapon", "knife", "unsupported_snapshot_weapon"),
        ("is_crouched", True, "unsupported_posture"),
        ("is_jumping", True, "unsupported_posture"),
        ("side", "counter-terrorist", "snapshot_side_mismatch"),
    ],
)
def test_explains_snapshot_exclusions(reader, field, value, reason):
    reader.snapshot_rows[0][field] = value
    assert run(reader).excluded[0].reason == reason


def test_missing_effect_fields_are_not_treated_as_absence(reader):
    reader.kill_rows[0].pop("penetrated")
    reader.kill_rows[0].pop("thrusmoke")
    reader.snapshot_rows[0]["is_blinded"] = None
    reader.snapshot_rows[0]["is_crouched"] = None
    scenario = run(reader).scenario_document.scenarios[0]
    assert {
        "penetration_unknown",
        "through_smoke_unknown",
        "player_flash_unknown",
        "player_posture_unknown",
    } <= set(scenario.limitations)


def test_flags_flash_without_claiming_unimpaired_duel(reader):
    reader.snapshot_rows[0]["is_blinded"] = True
    assert "player_blinded" in run(reader).scenario_document.scenarios[0].limitations


def test_ignores_untracked_snapshot_entities(reader):
    reader.snapshot_rows.append({**reader.snapshot_rows[0], "steamid": None})
    assert run(reader).eligible_candidates == 1


def test_duplicate_snapshot_identity_is_an_explicit_failure(reader):
    reader.snapshot_rows.append(deepcopy(reader.snapshot_rows[0]))
    with pytest.raises(DemoError, match="Ambiguous"):
        run(reader)


def test_group_counts_precede_selection_and_decode_ticks_once(reader):
    reader.kill_rows.append({**reader.kill_rows[0], "tick": 220})
    reader.damage_rows.extend([{**row, "tick": row["tick"] + 100} for row in reader.damage_rows])
    reader.snapshot_rows.extend([{**row, "tick": 199} for row in deepcopy(reader.snapshot_rows)])
    result = run(reader, max_scenarios=1, contact_window_ticks=64)
    assert reader.requested_ticks == [[99, 199]]
    assert reader.requested_location_ticks == [[99]]
    assert set(result.scenario_locations) == {
        item.scenario_id for item in result.scenario_document.scenarios
    }
    assert result.eligible_candidates == 2
    assert result.omitted_by_limit == 1
    assert result.groups[0].observations == 2
    assert len(result.groups[0].selected_scenario_ids) == 1
    assert len(result.scenario_document.scenarios) == 1
    assert "ranking_is_loss_frequency_not_win_rate" in result.limitations


@pytest.mark.parametrize("round_number", [13, 25, 31])
def test_side_changes_and_overtime_use_recorded_sides(reader, round_number):
    reader.round_rows[0]["round_num"] = round_number
    reader.kill_rows[0]["victim_side"] = "counter-terrorist"
    reader.kill_rows[0]["attacker_side"] = "terrorist"
    reader.snapshot_rows[0]["side"] = "counter-terrorist"
    reader.snapshot_rows[1]["side"] = "terrorist"
    scenario = run(reader).scenario_document.scenarios[0]
    assert scenario.source.round_number == round_number
    assert scenario.player.side == "CT"
    assert scenario.opponent.side == "T"


def test_no_eligible_deaths_returns_explicit_empty_analysis(reader):
    reader.kill_rows = []
    result = run(reader)
    assert result.deaths_considered == result.eligible_candidates == 0
    assert result.scenario_document is None
    assert result.status == "no_eligible_duels"
    assert result.groups == []
    assert reader.requested_ticks == []
    assert reader.requested_location_ticks == []
    assert result.scenario_locations == {}


def test_roster_excludes_bots_and_preserves_unicode_names(reader):
    result = roster(reader)
    assert len(result.players) == 2
    assert result.players[0].steam_id == str(PLAYER)
    assert result.players[1].name is None
    assert "roster_side_is_last_observed_not_historical" in result.limitations


def test_unknown_selected_player_is_an_error(reader):
    with pytest.raises(DemoError, match="not in"):
        analyze(lambda: reader, str(THIRD))


@pytest.mark.parametrize(
    "options",
    [
        {"max_scenarios": 0},
        {"contact_window_ticks": 0},
        {"group_cell_units": 0.0},
        {"group_cell_units": float("nan")},
    ],
)
def test_invalid_analysis_options_fail_explicitly(reader, options):
    with pytest.raises(DemoError):
        run(reader, **options)


def add_comparable_win(reader):
    reader.round_rows.append(
        {
            "round_num": 2,
            "start_tick": 501,
            "freeze_end_tick": 510,
            "end_tick": 1000,
            "is_knife_round": False,
        }
    )
    reader.kill_rows.append(
        {
            **reader.kill_rows[0],
            "tick": 720,
            "attacker_steamid": PLAYER,
            "victim_steamid": OPPONENT,
            "attacker_side": "terrorist",
            "victim_side": "counter-terrorist",
            "weapon": "ak47",
        }
    )
    reader.damage_rows.extend(
        [
            {
                "tick": tick,
                "attacker_steamid": PLAYER,
                "victim_steamid": OPPONENT,
                "weapon": "ak47",
            }
            for tick in (700, 720)
        ]
    )
    reader.snapshot_rows.extend([{**row, "tick": 699} for row in deepcopy(reader.snapshot_rows)])


def test_comparable_wins_use_selected_players_perspective_in_grouping(reader):
    add_comparable_win(reader)
    result = run(reader)
    assert result.analysis_version == 3
    assert result.deaths_considered == result.eligible_candidates == 1
    assert result.kills_considered == result.eligible_wins == 1
    assert result.excluded_wins == []
    assert len(result.groups) == 1
    group = result.groups[0]
    assert (group.observations, group.wins, group.losses, group.win_rate) == (2, 1, 1, 0.5)
    assert len(result.scenario_document.scenarios) == 1
    assert result.scenario_document.scenarios[0].source.death_tick == 120
    assert reader.requested_ticks == [[99, 699]]
    assert reader.requested_location_ticks == [[99]]


def test_angle_fallback_is_consistent_for_comparable_wins_and_losses(reader):
    add_comparable_win(reader)
    for row in reader.snapshot_rows:
        if row["steamid"] == OPPONENT:
            row.update(pitch=None, yaw=None)
    result = run(reader)
    assert result.eligible_candidates == result.eligible_wins == 1
    assert len(result.groups) == 1
    assert result.groups[0].win_rate == 0.5
    assert "opponent_aim_inferred_toward_player" in result.groups[0].context_limitations


def test_inferred_angles_are_not_grouped_with_recorded_angles(reader):
    add_comparable_win(reader)
    reader.snapshot_rows[1].update(pitch=None, yaw=None)
    result = run(reader)
    assert len(result.groups) == 2
    assert result.groups[0].win_rate == 0.0
    assert result.groups[1].win_rate == 1.0


@pytest.mark.parametrize("role", [0, 1])
def test_win_at_different_positions_does_not_inflate_loss_groups_win_rate(reader, role):
    add_comparable_win(reader)
    reader.snapshot_rows[2 + role]["x"] += 512
    result = run(reader)
    assert len(result.groups) == 2
    loss_group, win_group = result.groups
    assert (loss_group.wins, loss_group.losses, loss_group.win_rate) == (0, 1, 0.0)
    assert (win_group.wins, win_group.losses, win_group.win_rate) == (1, 0, 1.0)
    assert win_group.selected_scenario_ids == []


def test_excluded_win_is_not_counted_in_denominator_or_loss_exclusions(reader):
    add_comparable_win(reader)
    reader.kill_rows[1]["thrusmoke"] = True
    result = run(reader)
    assert result.excluded == []
    assert result.eligible_wins == 0
    assert result.kills_considered == 1
    assert result.excluded_wins[0].reason == "through_smoke"
    assert result.groups[0].observations == 1
    assert result.groups[0].win_rate == 0.0


def test_wins_require_the_same_complete_snapshot_as_losses(reader):
    add_comparable_win(reader)
    reader.snapshot_rows = reader.snapshot_rows[:-1]
    result = run(reader)
    assert result.eligible_candidates == 1
    assert result.eligible_wins == 0
    assert result.excluded_wins[0].reason == "missing_shared_snapshot"


def test_wins_only_report_does_not_create_training_scenarios(reader):
    add_comparable_win(reader)
    reader.kill_rows = reader.kill_rows[1:]
    result = run(reader)
    assert result.deaths_considered == 0
    assert result.eligible_wins == 1
    assert result.status == "no_eligible_duels"
    assert result.scenario_document is None
    assert result.groups[0].win_rate == 1.0
    assert "small_samples_do_not_establish_skill" in result.limitations


def test_self_kill_is_not_also_counted_as_a_win(reader):
    reader.kill_rows[0]["attacker_steamid"] = PLAYER
    result = run(reader)
    assert result.deaths_considered == 1
    assert result.kills_considered == result.eligible_wins == 0
    assert result.excluded_wins == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("is_blinded", True), ("is_blinded", None), ("is_crouched", None)],
)
def test_different_flash_or_unknown_posture_context_is_not_merged(reader, field, value):
    add_comparable_win(reader)
    reader.snapshot_rows[2][field] = value
    result = run(reader)
    assert len(result.groups) == 2
    assert result.groups[0].win_rate == 0.0
    assert result.groups[1].win_rate == 1.0


def test_group_metadata_explains_win_only_groups(reader):
    add_comparable_win(reader)
    reader.kill_rows = reader.kill_rows[1:]
    group = run(reader).groups[0]
    assert group.player_side == "T"
    assert group.player_weapon == "ak47"
    assert group.opponent_weapon == "m4a1"
    assert group.player_cell == (0, 0, 0)
    assert group.opponent_cell == (0, 0, 0)
    assert "map_geometry_unverified" in group.context_limitations
