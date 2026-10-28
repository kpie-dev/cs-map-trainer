import pytest
from pydantic import ValidationError

from cs_map_trainer.exporting import (
    ALLOWED_COMMANDS,
    MAX_CONSOLE_BYTES,
    MAX_COORDINATE,
    WEAPONS,
    ExportError,
    export_scenario,
)
from cs_map_trainer.scenarios import Scenario
from cs_map_trainer.weapons import GUNS


def test_exact_prototype_sequence(training_document):
    result = export_scenario(training_document.scenarios[0])
    assert result.commands == (
        "sv_cheats 1",
        "mp_limitteams 0",
        "mp_autoteambalance 0",
        "bot_quota_mode normal",
        "bot_quota 0",
        "bot_stop 1",
        "bot_kick",
        "jointeam 2",
        "bot_add_ct",
        "ent_setname cmt_v1_bot 2",
        "setpos_player 2 4.0 5.0 6.0",
        "ent_remove cmt_v1_teleport",
        'ent_create point_teleport { targetname cmt_v1_teleport origin "4.0 5.0 6.0" '
        'angles "0 -135.0 0" teleport_use_current_angle 0 }',
        "ent_fire cmt_v1_teleport TeleportEntityToCurrentPos cmt_v1_bot",
        "ent_fire cmt_v1_teleport Kill",
        "setpos_exact 1.0 2.0 3.0",
        "setang_exact 0 45.0 0",
        'say "weapon ak47"',
        'say "botweapon m4a1"',
    )
    assert "\n" not in result.console_line
    assert result.console_line == "; ".join(result.commands)
    assert result.cfg.splitlines()[1:] == list(result.commands)
    assert "unverified_in_game" in result.cfg.splitlines()[0]
    assert len(result.console_line.encode("ascii")) <= MAX_CONSOLE_BYTES


def test_ct_player_uses_t_bot_and_original_aim(training_document):
    scenario = training_document.scenarios[0]
    scenario.player.side, scenario.opponent.side = "CT", "T"
    scenario.player.view_angles.pitch = -12.345678901234
    scenario.opponent.view_angles.pitch = 50.0
    result = export_scenario(scenario)
    assert "jointeam 3" in result.commands
    assert "bot_add_t" in result.commands
    assert "setang_exact -12.345678901234 45.0 0" in result.commands
    assert 'angles "50.0 -135.0 0"' in result.console_line


@pytest.mark.parametrize("weapon", sorted(GUNS))
def test_all_analysis_firearms_have_explicit_mapping(training_document, weapon):
    scenario = training_document.scenarios[0]
    scenario.player.weapon = scenario.opponent.weapon = weapon
    result = export_scenario(scenario)
    assert f'say "weapon {WEAPONS[weapon]}"' in result.commands
    assert f'say "botweapon {WEAPONS[weapon]}"' in result.commands


@pytest.mark.parametrize("participant", ["player", "opponent"])
@pytest.mark.parametrize("value", [-MAX_COORDINATE, MAX_COORDINATE, -0.0, 0.0000001])
def test_coordinate_boundaries_and_small_numbers(training_document, participant, value):
    scenario = training_document.scenarios[0]
    getattr(scenario, participant).position.x = float(value)
    result = export_scenario(scenario)
    assert "e-" not in result.console_line
    assert "-0.0" not in result.console_line


@pytest.mark.parametrize("participant", ["player", "opponent"])
@pytest.mark.parametrize("axis", ["pitch", "yaw"])
@pytest.mark.parametrize("direction", [-1, 1])
def test_angle_bounds_are_preserved(training_document, participant, axis, direction):
    scenario = training_document.scenarios[0]
    value = float(direction * (90 if axis == "pitch" else 180))
    setattr(getattr(scenario, participant).view_angles, axis, value)
    assert str(value) in export_scenario(scenario).console_line


@pytest.mark.parametrize("participant", ["player", "opponent"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("weapon", "knife"),
        ("weapon", "weapon_ak47"),
        ("weapon", "ak47;quit"),
        ("weapon", 'ak47"\nsay secret'),
        ("position.x", MAX_COORDINATE + 0.1),
        ("position.z", -MAX_COORDINATE - 0.1),
        ("position.y", float("nan")),
        ("position.y", float("inf")),
        ("view_angles.pitch", 91.0),
        ("view_angles.yaw", -181.0),
        ("view_angles.roll", 1.0),
    ],
)
def test_revalidates_mutated_models(training_document, participant, field, value):
    scenario = training_document.scenarios[0]
    target = getattr(scenario, participant)
    *parents, field = field.split(".")
    for parent in parents:
        target = getattr(target, parent)
    setattr(target, field, value)
    with pytest.raises((ExportError, ValidationError)):
        export_scenario(scenario)


def test_untrusted_metadata_is_not_console_code(training_document):
    scenario = training_document.scenarios[0]
    before = export_scenario(scenario)
    data = scenario.model_dump()
    data["map"]["revision"] = 'private;quit;"'
    data["source"]["parser_version"] = "private;quit"
    data["limitations"].append("private")
    data["scenario_id"] = "private"
    after = export_scenario(Scenario.model_validate(data))
    assert before.commands == after.commands
    assert "private" not in after.console_line


def test_no_binds_waits_scripts_or_broad_entity_cleanup(training_document):
    result = export_scenario(training_document.scenarios[0])
    assert {command.split()[0] for command in result.commands} <= ALLOWED_COMMANDS
    for token in ("bind", "autoexec", "wait", "sleep", "mimic", "ent_remove_all", "!picker"):
        assert token not in result.console_line
    removals = [command for command in result.commands if command.startswith("ent_remove ")]
    assert removals == ["ent_remove cmt_v1_teleport"]
    assert result == export_scenario(training_document.scenarios[0])


def test_synthetic_nonplayable_fixture_is_rejected(payload):
    payload["scenarios"][0]["map"]["name"] = "de_mirage"
    with pytest.raises(ExportError, match="non-playable"):
        export_scenario(Scenario.model_validate(payload["scenarios"][0]))


def test_unsupported_map_is_rejected(training_document):
    scenario = training_document.scenarios[0]
    scenario.map.name = "de_inferno"
    with pytest.raises(ExportError, match="de_mirage"):
        export_scenario(scenario)


def test_too_long_single_paste_is_an_explicit_error(training_document):
    scenario = training_document.scenarios[0]
    for participant in (scenario.player, scenario.opponent):
        for field in ("x", "y", "z"):
            setattr(participant.position, field, 5e-324)
    with pytest.raises(ExportError, match="byte budget"):
        export_scenario(scenario)
