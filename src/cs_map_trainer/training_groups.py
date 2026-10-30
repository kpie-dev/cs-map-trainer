"""Conservative practice grouping, separate from the parser's duel statistics."""

import hashlib
import math
from dataclasses import dataclass

from .scenarios import Scenario

WEAPON_CLASSES = {
    **dict.fromkeys("ak47 aug famas galilar m4a1 m4a1_silencer sg556".split(), "rifle"),
    **dict.fromkeys("awp g3sg1 scar20".split(), "sniper"),
    **dict.fromkeys(
        "cz75a deagle elite fiveseven glock hkp2000 p250 revolver tec9 usp_silencer".split(),
        "pistol",
    ),
    **dict.fromkeys("bizon mac10 mp5sd mp7 mp9 p90 ump45".split(), "smg"),
    **dict.fromkeys("mag7 nova sawedoff xm1014".split(), "shotgun"),
    **dict.fromkeys("m249 negev".split(), "machine_gun"),
    "ssg08": "scout",
}
PRIORITY_LABELS = (
    "Full gun vs pistol/SMG",
    "Full gun vs full gun",
    "Other / unknown weapon matchup",
    "Own pistol/SMG",
)


def weapon_class(weapon):
    return WEAPON_CLASSES.get(weapon, f"unknown:{weapon}")


def practice_priority(scenario):
    player, opponent = (
        weapon_class(scenario.player.weapon),
        weapon_class(scenario.opponent.weapon),
    )
    if player in {"rifle", "sniper"}:
        if opponent in {"pistol", "smg"}:
            return 0
        if opponent in {"rifle", "sniper"}:
            return 1
    if player in {"pistol", "smg"}:
        return 3
    return 2


def _compatible(left, right):
    if (
        left.map != right.map
        or left.source.demo_sha256 != right.source.demo_sha256
        or left.source.parser_name != right.source.parser_name
        or left.player.steam_id != right.player.steam_id
        or left.player.side != right.player.side
        or left.opponent.side != right.opponent.side
        or set(left.limitations) != set(right.limitations)
        or (left.source.parser_version, left.source.rules_version)
        != (right.source.parser_version, right.source.rules_version)
    ):
        return False
    for role in ("player", "opponent"):
        a, b = getattr(left, role), getattr(right, role)
        if weapon_class(a.weapon) != weapon_class(b.weapon):
            return False
        if (
            math.dist(
                (a.position.x, a.position.y, a.position.z),
                (b.position.x, b.position.y, b.position.z),
            )
            > 192
            or abs(a.position.z - b.position.z) > 64
            or abs(a.view_angles.pitch - b.view_angles.pitch) > 20
            or abs((a.view_angles.yaw - b.view_angles.yaw + 180) % 360 - 180) > 30
            or a.view_angles.roll != b.view_angles.roll
        ):
            return False
    return True


@dataclass(frozen=True)
class TrainingGroup:
    group_id: str
    members: list[Scenario]

    @property
    def scenario_ids(self):
        return [item.scenario_id for item in self.members]

    @property
    def priority(self):
        return practice_priority(self.members[0])

    @property
    def priority_label(self):
        return PRIORITY_LABELS[self.priority]


def training_groups(document):
    """Complete-link groups: every pair must pass, so nearby chains cannot bridge sites."""
    buckets = []
    for scenario in sorted(document.scenarios, key=lambda item: item.scenario_id):
        bucket = next(
            (items for items in buckets if all(_compatible(scenario, item) for item in items)),
            None,
        )
        if bucket is None:
            buckets.append([scenario])
        else:
            bucket.append(scenario)
    groups = [
        TrainingGroup(
            "practice-"
            + hashlib.sha256("\n".join(s.scenario_id for s in items).encode()).hexdigest()[:16],
            items,
        )
        for items in buckets
    ]
    return sorted(groups, key=lambda group: (group.priority, group.group_id))


def expand_group_selection(document, included, partial):
    """Validate form group IDs and explicit partial snapshots; never infer extra members."""
    groups = {group.group_id: group for group in training_groups(document)}
    if len(included) != len(set(included)) or not set(included) <= groups.keys():
        raise ValueError("Duplicate or unknown group")
    preserved = set()
    for gid, value in partial.items():
        if gid not in groups or set(value) != {"action", "members"}:
            raise ValueError("Unknown partial group")
        members = value["members"]
        if (
            value["action"] not in {"preserve", "clear"}
            or len(members) != len(set(members))
            or not members
            or not set(members) < set(groups[gid].scenario_ids)
        ):
            raise ValueError("Invalid partial membership")
        if value["action"] == "preserve":
            preserved.update(members)
    return [
        sid
        for gid, group in groups.items()
        for sid in group.scenario_ids
        if gid in included or sid in preserved
    ]
