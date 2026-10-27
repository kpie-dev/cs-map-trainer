import json

import pytest
from pydantic import ValidationError

from cs_map_trainer.scenarios import ScenarioDocument


def test_synthetic_document_roundtrip(payload):
    document = ScenarioDocument.model_validate(payload)
    assert ScenarioDocument.model_validate_json(document.model_dump_json()) == document
    assert document.scenarios[0].player.view_angles.yaw == 45


@pytest.mark.parametrize("version", [0, 2, True, "1", 1.0, None])
def test_rejects_unsupported_or_coerced_version(payload, version):
    payload["schema_version"] = version
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize("field", ["map", "source", "player", "opponent", "limitations"])
def test_requires_scenario_fields(payload, field):
    del payload["scenarios"][0][field]
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_tick", -1),
        ("snapshot_tick", 120),
        ("contact_tick", 99),
        ("contact_tick", 121),
        ("death_tick", 99),
        ("round_number", 0),
        ("snapshot_tick", True),
        ("demo_sha256", "not-a-hash"),
    ],
)
def test_rejects_invalid_source(payload, field, value):
    payload["scenarios"][0]["source"][field] = value
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


def test_single_hit_death_is_allowed(payload):
    payload["scenarios"][0]["source"]["contact_tick"] = 120
    ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1"])
def test_rejects_invalid_coordinate(payload, value):
    payload["scenarios"][0]["player"]["position"]["x"] = value
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize(("field", "value"), [("pitch", 91), ("yaw", -181), ("roll", 181)])
def test_rejects_invalid_angles(payload, field, value):
    payload["scenarios"][0]["player"]["view_angles"][field] = value
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize("field", ["steam_id", "side"])
def test_rejects_self_or_team_duel(payload, field):
    scenario = payload["scenarios"][0]
    scenario["opponent"][field] = scenario["player"][field]
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


@pytest.mark.parametrize("value", ["", "ak47;quit", "ak47\nquit", "../autoexec", "ak47 "])
def test_weapon_is_a_token_not_a_command(payload, value):
    payload["scenarios"][0]["player"]["weapon"] = value
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


def test_rejects_duplicate_ids(payload):
    payload["scenarios"] *= 2
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate(payload)


def test_rejects_empty_document():
    with pytest.raises(ValidationError):
        ScenarioDocument(schema_version=1, scenarios=[])


@pytest.mark.parametrize("location", ["document", "scenario", "position"])
def test_rejects_unknown_fields(payload, location):
    target = payload
    if location != "document":
        target = payload["scenarios"][0]
    if location == "position":
        target = target["player"]["position"]
    target["unexpected"] = "value"
    with pytest.raises(ValidationError):
        ScenarioDocument.model_validate_json(json.dumps(payload))
