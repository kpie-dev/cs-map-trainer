from copy import deepcopy

import pytest

from cs_map_trainer.scenarios import ScenarioDocument
from cs_map_trainer.training_groups import (
    WEAPON_CLASSES,
    expand_group_selection,
    practice_priority,
    training_groups,
    weapon_class,
)
from cs_map_trainer.weapons import GUNS


def scenarios(payload, count=3):
    base = payload["scenarios"][0]
    items = []
    for i in range(count):
        item = deepcopy(base)
        item["scenario_id"] = f"duel-{i}"
        item["player"]["weapon"] = "ak47"
        item["opponent"]["weapon"] = "m4a1_silencer"
        items.append(item)
    return items


def document(items):
    return ScenarioDocument(schema_version=1, scenarios=items)


def test_all_canonical_weapons_are_explicit_and_unknown_is_neutral():
    assert set(WEAPON_CLASSES) == GUNS
    assert weapon_class("future_gun") == "unknown:future_gun"


def test_group_contains_all_similar_members_not_only_a_representative(payload):
    items = scenarios(payload)
    items[1]["player"]["weapon"] = "m4a1_silencer"
    items[2]["player"]["weapon"] = "galilar"
    items[1]["player"]["position"]["x"] += 50
    groups = training_groups(
        ScenarioDocument.model_validate({"schema_version": 1, "scenarios": items})
    )
    assert len(groups) == 1
    assert groups[0].scenario_ids == ["duel-0", "duel-1", "duel-2"]
    assert (
        expand_group_selection(document(groups[0].members), [groups[0].group_id], {})
        == groups[0].scenario_ids
    )
    reversed_document = document(list(reversed(groups[0].members)))
    assert training_groups(reversed_document) == groups


@pytest.mark.parametrize(
    "change",
    ["distance", "height", "yaw", "pitch", "context", "side", "map", "weapon", "unknown"],
)
def test_incompatible_snapshots_are_not_grouped(payload, change):
    items = scenarios(payload, 2)
    changed = items[1]
    if change == "distance":
        changed["opponent"]["position"]["x"] += 193
    elif change == "height":
        changed["player"]["position"]["z"] += 65
    elif change == "yaw":
        changed["player"]["view_angles"]["yaw"] = (
            changed["player"]["view_angles"]["yaw"] + 31 + 180
        ) % 360 - 180
    elif change == "pitch":
        changed["player"]["view_angles"]["pitch"] = 60.0
    elif change == "context":
        changed["limitations"].append("player_blinded")
    elif change == "side":
        changed["player"]["side"], changed["opponent"]["side"] = (
            changed["opponent"]["side"],
            changed["player"]["side"],
        )
    elif change == "map":
        changed["map"]["revision"] = "other-revision"
    elif change == "weapon":
        changed["player"]["weapon"] = "awp"
    else:
        changed["player"]["weapon"] = "future_gun"
    doc = ScenarioDocument.model_validate({"schema_version": 1, "scenarios": items})
    assert len(training_groups(doc)) == 2


def test_complete_link_prevents_distant_chain_merging(payload):
    items = scenarios(payload)
    for index, item in enumerate(items):
        item["player"]["position"]["x"] += index * 150
    groups = training_groups(
        ScenarioDocument.model_validate({"schema_version": 1, "scenarios": items})
    )
    assert sorted(len(group.members) for group in groups) == [1, 2]


@pytest.mark.parametrize(
    "player,opponent,priority",
    [
        ("awp", "tec9", 0),
        ("ak47", "mp9", 0),
        ("ak47", "m4a1_silencer", 1),
        ("awp", "ak47", 1),
        ("m4a1_silencer", "awp", 1),
        ("ssg08", "ak47", 2),
        ("negev", "glock", 2),
        ("nova", "usp_silencer", 2),
        ("future_gun", "glock", 2),
        ("ak47", "future_gun", 2),
        ("glock", "awp", 3),
        ("mp9", "glock", 3),
    ],
)
def test_weapon_priority_is_explicit_not_actual_economy(payload, player, opponent, priority):
    item = scenarios(payload, 1)[0]
    item["player"]["weapon"], item["opponent"]["weapon"] = player, opponent
    doc = ScenarioDocument.model_validate({"schema_version": 1, "scenarios": [item]})
    assert practice_priority(doc.scenarios[0]) == priority


def test_partial_selection_is_exact_explicit_and_repeatable(payload):
    doc = ScenarioDocument.model_validate({"schema_version": 1, "scenarios": scenarios(payload)})
    group = training_groups(doc)[0]
    partial = {group.group_id: {"action": "preserve", "members": ["duel-1"]}}
    assert expand_group_selection(doc, [], partial) == ["duel-1"]
    assert expand_group_selection(doc, [group.group_id], partial) == group.scenario_ids
    partial[group.group_id]["action"] = "clear"
    assert expand_group_selection(doc, [], partial) == []


@pytest.mark.parametrize(
    "kind", ["unknown", "duplicate", "member", "all", "action", "cross", "duplicate-member"]
)
def test_group_selection_strict_validation(payload, kind):
    items = scenarios(payload)
    items[2]["player"]["position"]["x"] += 1000
    doc = ScenarioDocument.model_validate({"schema_version": 1, "scenarios": items})
    group = next(group for group in training_groups(doc) if len(group.members) == 2)
    included, partial = [], {}
    if kind == "unknown":
        included = ["missing"]
    elif kind == "duplicate":
        included = [group.group_id, group.group_id]
    else:
        partial = {
            group.group_id: {
                "action": "not-an-action" if kind == "action" else "preserve",
                "members": group.scenario_ids
                if kind == "all"
                else ["missing" if kind == "member" else "duel-2" if kind == "cross" else "duel-0"],
            }
        }
        if kind == "duplicate-member":
            partial[group.group_id]["members"] = ["duel-0", "duel-0"]
    with pytest.raises(ValueError):
        expand_group_selection(doc, included, partial)
