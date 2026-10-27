"""Opt-in local demo tests; never download or publish user data."""

import math
import os
from collections import Counter
from pathlib import Path

import pytest

from cs_map_trainer.analysis import analyze, roster
from cs_map_trainer.parsing import DemoReader
from cs_map_trainer.scenarios import ScenarioDocument


@pytest.fixture(scope="module")
def demo_path():
    value = os.environ.get("CS_MAP_TRAINER_DEMO")
    if not value:
        pytest.skip("Set CS_MAP_TRAINER_DEMO to an authorized local Mirage .dem")
    return Path(value)


def test_real_demo_pipeline(demo_path):
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
    document = ScenarioDocument.model_validate_json(report.scenario_document.model_dump_json())
    assert len(document.scenarios) <= 10
    ticks = sorted({scenario.source.snapshot_tick for scenario in document.scenarios})
    snapshots = reader.snapshots(ticks).to_dicts()
    for scenario in document.scenarios:
        assert scenario.source.snapshot_tick < scenario.source.contact_tick
        assert scenario.source.contact_tick <= scenario.source.death_tick
        for participant in (scenario.player, scenario.opponent):
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
