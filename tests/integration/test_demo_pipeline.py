"""Opt-in local demo tests; never download or publish user data."""

import math
import os
import shutil
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from cs_map_trainer.analysis import analyze, roster
from cs_map_trainer.exporting import export_scenario
from cs_map_trainer.packs import build_pack, load_scenarios
from cs_map_trainer.parsing import DemoReader
from cs_map_trainer.scenarios import ScenarioDocument


@pytest.fixture(scope="module")
def demo_path():
    value = os.environ.get("CS_MAP_TRAINER_DEMO")
    if not value:
        pytest.skip("Set CS_MAP_TRAINER_DEMO to an authorized local supported-map CS2 .dem")
    return Path(value)


def test_real_demo_pipeline(demo_path, tmp_path):
    reader = DemoReader(demo_path)
    players = roster(reader)
    _, kills, _ = reader.combat()
    selected_id = str(
        Counter(
            row["victim_steamid"] for row in kills.to_dicts() if row["victim_steamid"]
        ).most_common(1)[0][0]
    )
    assert selected_id in {player.steam_id for player in players.players}
    report = analyze(lambda: DemoReader(demo_path), selected_id)
    assert report.deaths_considered == report.eligible_candidates + len(report.excluded)
    assert report.kills_considered == report.eligible_wins + len(report.excluded_wins)
    assert sum(group.losses for group in report.groups) == report.eligible_candidates
    assert sum(group.wins for group in report.groups) == report.eligible_wins
    assert all(
        group.win_rate == group.wins / group.observations
        and group.observations == group.wins + group.losses
        for group in report.groups
    )
    assert report.eligible_candidates > 0
    assert report.analysis_version == 3
    document = ScenarioDocument.model_validate_json(report.scenario_document.model_dump_json())
    assert report.map == reader.map
    assert all(scenario.map == report.map for scenario in document.scenarios)
    pack = build_pack(load_scenarios(report.model_dump_json().encode()), include_cfg=True)
    assert pack.manifest.compatibility == "unverified_in_game"
    assert [entry.map for entry in pack.manifest.entries] == [
        scenario.map for scenario in document.scenarios
    ]
    assert len(document.scenarios) <= 10
    ticks = sorted({scenario.source.snapshot_tick for scenario in document.scenarios})
    snapshots = reader.snapshots(ticks).to_dicts()
    native_locations = reader.demo.ticks(props=["m_szLastPlaceName"], players_only=True)
    native_locations = native_locations.filter(pl.col("tick").is_in(ticks)).to_dicts()
    assert set(report.scenario_locations) == {
        scenario.scenario_id for scenario in document.scenarios
    }
    for scenario in document.scenarios:
        assert scenario.source.snapshot_tick < scenario.source.contact_tick
        assert scenario.source.contact_tick <= scenario.source.death_tick
        locations = report.scenario_locations[scenario.scenario_id]
        assert locations.snapshot_tick == scenario.source.snapshot_tick
        assert locations.source == "m_szLastPlaceName"
        for role, participant in (("player", scenario.player), ("opponent", scenario.opponent)):
            reference = next(
                row
                for row in snapshots
                if row["tick"] == scenario.source.snapshot_tick
                and str(row["steamid"]) == participant.steam_id
            )
            assert participant.position.x == reference["x"]
            assert participant.position.y == reference["y"]
            assert participant.position.z == reference["z"]
            pitch, yaw = reference.get("pitch"), reference.get("yaw")
            if pitch is None or yaw is None:
                assert participant is scenario.opponent
                assert "opponent_aim_inferred_toward_player" in scenario.limitations
                dx = scenario.player.position.x - participant.position.x
                dy = scenario.player.position.y - participant.position.y
                dz = scenario.player.position.z - participant.position.z
                if pitch is None:
                    pitch = -math.degrees(math.atan2(dz, math.hypot(dx, dy)))
                if yaw is None:
                    yaw = math.degrees(math.atan2(dy, dx))
            assert participant.view_angles.pitch == pytest.approx(pitch)
            assert participant.view_angles.yaw == pytest.approx((yaw + 180) % 360 - 180)
            native = next(
                row["m_szLastPlaceName"]
                for row in native_locations
                if row["tick"] == scenario.source.snapshot_tick
                and str(row["steamid"]) == participant.steam_id
            )
            assert native, "Expected location coverage in the authorized integration fixture"
            assert getattr(locations, role) == native.strip()

    from cs_map_trainer.web.tasks import run_parser

    input_path = tmp_path / "input.dem"
    shutil.copyfile(demo_path, input_path)
    try:
        worker_report, scripts = run_parser(SimpleNamespace(player_steam_id=selected_id), tmp_path)
    finally:
        input_path.unlink()
        (tmp_path / "result.json").unlink(missing_ok=True)
    assert worker_report["map"] == report.map.model_dump()
    assert worker_report["eligible_candidates"] == report.eligible_candidates
    assert worker_report["eligible_wins"] == report.eligible_wins
    assert worker_report["scenario_document"] == document.model_dump(mode="json")
    assert worker_report["scenario_locations"] == {
        scenario_id: locations.model_dump(mode="json")
        for scenario_id, locations in report.scenario_locations.items()
    }
    assert scripts == [
        {
            "scenario_id": scenario.scenario_id,
            "console_line": export_scenario(scenario).console_line,
            "error": None,
        }
        for scenario in document.scenarios
    ]
