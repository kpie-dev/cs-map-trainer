"""Conservative, damage-based duel candidates; not a tactical error detector."""

import math
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Annotated, Literal, Protocol

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cs_map_trainer.parsing import PARSER_VERSION, DemoError
from cs_map_trainer.scenarios import (
    ContractModel,
    MapIdentity,
    Participant,
    Position,
    Scenario,
    ScenarioDocument,
    Source,
    SteamID,
    ViewAngles,
)
from cs_map_trainer.weapons import GUNS

RULES_VERSION = "damage-window-v3"
SIDES = {"terrorist": "T", "counter-terrorist": "CT"}
BASE_LIMITATIONS = [
    "map_geometry_unverified",
    "contact_inferred_from_damage",
    "static_positions_only",
    "smoke_visibility_not_evaluated",
    "movement_not_reconstructed",
    "health_armor_not_reconstructed",
    "bot_behavior_not_reconstructed",
    "roll_not_recorded",
]


class Reader(Protocol):
    map: MapIdentity
    sha256: str
    size_bytes: int

    def players(self) -> pl.DataFrame: ...
    def combat(self) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]: ...
    def snapshots(self, ticks: list[int]) -> pl.DataFrame: ...


class ParserRow(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class PlayerRow(ParserRow):
    steamid: int
    name: str | None
    side: str | None


class RoundRow(ParserRow):
    round_num: int
    start_tick: int
    freeze_end_tick: int | None
    end_tick: int | None
    is_knife_round: bool | None = None


class DamageRow(ParserRow):
    tick: int
    attacker_steamid: int | None
    victim_steamid: int | None
    weapon: str | None


class KillRow(DamageRow):
    attacker_side: str | None
    victim_side: str | None
    penetrated: int | None = None
    thrusmoke: bool | None = None


class SnapshotRow(ParserRow):
    tick: int
    steamid: int
    side: str | None
    x: float | None
    y: float | None
    z: float | None
    pitch: float | None = None
    yaw: float | None = None
    health: int | None
    active_weapon: str | None
    is_crouched: bool | None
    is_jumping: bool | None
    is_blinded: bool | None

    def participant(self, *, aim_target: Position | None = None) -> Participant:
        if self.side not in SIDES:
            raise DemoError("unknown_snapshot_side")
        if self.health is None or self.health <= 0:
            raise DemoError("missing_or_dead_snapshot_participant")
        if self.is_crouched or self.is_jumping:
            raise DemoError("unsupported_posture")
        if self.active_weapon not in GUNS:
            raise DemoError("unsupported_snapshot_weapon")
        if any(value is None for value in (self.x, self.y, self.z)):
            raise DemoError("missing_snapshot_position_or_angles")
        position = Position(x=self.x, y=self.y, z=self.z)
        pitch, yaw = self.pitch, self.yaw
        if pitch is None or yaw is None:
            if aim_target is None:
                raise DemoError("missing_snapshot_position_or_angles")
            dx, dy, dz = (
                aim_target.x - position.x,
                aim_target.y - position.y,
                aim_target.z - position.z,
            )
            if not all(math.isfinite(value) for value in (dx, dy, dz)):
                raise DemoError("invalid_snapshot_values")
            horizontal = math.hypot(dx, dy)
            if (horizontal == 0 and dz == 0) or (horizontal == 0 and yaw is None):
                raise DemoError("undefined_opponent_aim_direction")
            if pitch is None:
                # Source pitch is negative when looking up; equal standing eye heights are assumed.
                pitch = -math.degrees(math.atan2(dz, horizontal))
            if yaw is None:
                yaw = math.degrees(math.atan2(dy, dx))
        yaw = (yaw + 180) % 360 - 180
        return Participant(
            steam_id=str(self.steamid),
            side=SIDES[self.side],
            position=position,
            view_angles=ViewAngles(pitch=pitch, yaw=yaw, roll=0.0),
            weapon=self.active_weapon,
        )


class RosterPlayer(ContractModel):
    steam_id: SteamID
    name: str | None
    last_observed_side: str | None


class Roster(ContractModel):
    map: MapIdentity
    players: list[RosterPlayer]
    limitations: list[str]


class ExcludedDuel(ContractModel):
    death_tick: int
    reason: str


class DuelGroup(ContractModel):
    group_id: str
    observations: int
    wins: int
    losses: int
    win_rate: float
    player_side: Literal["T", "CT"]
    player_weapon: str
    opponent_weapon: str
    player_cell: tuple[int, int, int]
    opponent_cell: tuple[int, int, int]
    context_limitations: list[str]
    selected_scenario_ids: list[str]


class Metrics(ContractModel):
    wall_seconds: float
    cpu_seconds: float
    process_peak_rss_bytes: int | None
    rss_scope: Literal["process_lifetime", "unavailable_on_platform"]
    input_block_operations: int | None = None
    output_block_operations: int | None = None
    input_bytes: int


class AnalysisReport(ContractModel):
    analysis_version: Annotated[int, Field(ge=2, le=2)] = 2
    status: Literal["candidates_ready", "no_eligible_duels"]
    parser_version: str
    rules_version: str
    player_steam_id: SteamID
    demo_sha256: str
    map: MapIdentity
    contact_window_ticks: int
    group_cell_units: float
    deaths_considered: int
    kills_considered: int
    eligible_candidates: int
    eligible_wins: int
    omitted_by_limit: int
    excluded: list[ExcludedDuel]
    excluded_wins: list[ExcludedDuel]
    groups: list[DuelGroup]
    scenario_document: ScenarioDocument | None
    limitations: list[str]
    metrics: Metrics


def roster(reader: Reader) -> Roster:
    players = [PlayerRow.model_validate(row) for row in reader.players().to_dicts()]
    return Roster(
        map=reader.map,
        players=[
            RosterPlayer(
                steam_id=str(player.steamid),
                name=player.name,
                last_observed_side=SIDES.get(player.side),
            )
            for player in sorted(players, key=lambda player: player.steamid)
            if player.steamid != 0
        ],
        limitations=["roster_side_is_last_observed_not_historical", "map_geometry_unverified"],
    )


def _round_for(tick: int, rounds: list[RoundRow]) -> RoundRow | None:
    return next(
        (
            row
            for row in rounds
            if row.freeze_end_tick is not None
            and row.end_tick is not None
            and row.freeze_end_tick <= tick <= row.end_tick
        ),
        None,
    )


def _kill_exclusion(kill: KillRow, round_row: RoundRow | None) -> str | None:
    if round_row is None:
        return "outside_live_round"
    if round_row.is_knife_round is True:
        return "knife_round"
    if not kill.attacker_steamid or kill.attacker_steamid == kill.victim_steamid:
        return "world_or_suicide"
    if kill.attacker_side not in SIDES or kill.victim_side not in SIDES:
        return "unknown_side"
    if kill.attacker_side == kill.victim_side:
        return "teamkill"
    if kill.weapon not in GUNS:
        return "unsupported_killing_weapon"
    if kill.penetrated is not None and kill.penetrated > 0:
        return "penetration"
    if kill.thrusmoke:
        return "through_smoke"
    return None


def _position_cell(position: Position, cell: float) -> tuple[int, int, int]:
    return (
        math.floor(position.x / cell),
        math.floor(position.y / cell),
        math.floor(position.z / cell),
    )


def _group_key(scenario: Scenario, cell: float) -> tuple:
    return (
        scenario.player.side,
        scenario.player.weapon,
        scenario.opponent.weapon,
        _position_cell(scenario.player.position, cell),
        _position_cell(scenario.opponent.position, cell),
        tuple(sorted(scenario.limitations)),
    )


def analyze(
    open_reader: Callable[[], Reader],
    steam_id: str,
    *,
    max_scenarios: int = 10,
    contact_window_ticks: int = 128,
    group_cell_units: float = 256.0,
) -> AnalysisReport:
    started, cpu_started = time.perf_counter(), time.process_time()
    if max_scenarios < 1 or contact_window_ticks < 1:
        raise DemoError("Scenario limit and contact window must be positive")
    if not math.isfinite(group_cell_units) or group_cell_units <= 0:
        raise DemoError("Group cell size must be finite and positive")
    reader = open_reader()
    if steam_id not in {player.steam_id for player in roster(reader).players}:
        raise DemoError("Selected SteamID is not in this demo's roster")
    rounds_frame, kills_frame, damages_frame = reader.combat()
    rounds = [RoundRow.model_validate(row) for row in rounds_frame.to_dicts()]
    kills = [KillRow.model_validate(row) for row in kills_frame.to_dicts()]
    kills = [
        kill
        for kill in kills
        if str(kill.victim_steamid) == steam_id or str(kill.attacker_steamid) == steam_id
    ]
    damages = [DamageRow.model_validate(row) for row in damages_frame.to_dicts()]
    excluded: list[ExcludedDuel] = []
    excluded_wins: list[ExcludedDuel] = []

    def reject(kill: KillRow, reason: str) -> None:
        target = excluded if str(kill.victim_steamid) == steam_id else excluded_wins
        target.append(ExcludedDuel(death_tick=kill.tick, reason=reason))

    candidates: list[tuple[KillRow, RoundRow, int]] = []
    for kill in sorted(kills, key=lambda kill: kill.tick):
        round_row = _round_for(kill.tick, rounds)
        reason = _kill_exclusion(kill, round_row)
        if reason:
            reject(kill, reason)
            continue
        pair = {kill.victim_steamid, kill.attacker_steamid}
        window_start = max(round_row.freeze_end_tick, kill.tick - contact_window_ticks)
        exchange = [
            damage
            for damage in damages
            if window_start <= damage.tick <= kill.tick
            and {damage.attacker_steamid, damage.victim_steamid} == pair
            and damage.weapon in GUNS
        ]
        if not exchange:
            reject(kill, "missing_damage_contact")
            continue
        contact = min(damage.tick for damage in exchange)
        if contact <= round_row.freeze_end_tick:
            reject(kill, "no_pre_contact_live_tick")
            continue
        if any(
            contact <= damage.tick <= kill.tick
            and pair.intersection((damage.attacker_steamid, damage.victim_steamid))
            and {damage.attacker_steamid, damage.victim_steamid} != pair
            for damage in damages
        ):
            reject(kill, "multi_party_damage")
            continue
        candidates.append((kill, round_row, contact))

    ticks = sorted({contact - 1 for _, _, contact in candidates})
    needed = {
        (contact - 1, steamid)
        for kill, _, contact in candidates
        for steamid in (kill.victim_steamid, kill.attacker_steamid)
    }
    snapshots: dict[tuple[int, int], SnapshotRow] = {}
    if ticks:
        for row in reader.snapshots(ticks).to_dicts():
            if (row.get("tick"), row.get("steamid")) not in needed:
                continue
            snapshot = SnapshotRow.model_validate(row)
            key = (snapshot.tick, snapshot.steamid)
            if key in snapshots:
                raise DemoError("Ambiguous duplicate player snapshot at the same tick")
            snapshots[key] = snapshot

    scenarios: list[Scenario] = []
    wins: list[Scenario] = []
    for index, (kill, round_row, contact) in enumerate(candidates, start=1):
        lost = str(kill.victim_steamid) == steam_id
        player_id = kill.victim_steamid if lost else kill.attacker_steamid
        opponent_id = kill.attacker_steamid if lost else kill.victim_steamid
        player_side = kill.victim_side if lost else kill.attacker_side
        opponent_side = kill.attacker_side if lost else kill.victim_side
        player = snapshots.get((contact - 1, player_id))
        opponent = snapshots.get((contact - 1, opponent_id))
        if player is None or opponent is None:
            reject(kill, "missing_shared_snapshot")
            continue
        limitations = list(BASE_LIMITATIONS)
        for role, snapshot in (("player", player), ("opponent", opponent)):
            if snapshot.is_blinded is True:
                limitations.append(f"{role}_blinded")
            elif snapshot.is_blinded is None:
                limitations.append(f"{role}_flash_unknown")
            if snapshot.is_crouched is None or snapshot.is_jumping is None:
                limitations.append(f"{role}_posture_unknown")
        if kill.penetrated is None:
            limitations.append("penetration_unknown")
        if kill.thrusmoke is None:
            limitations.append("through_smoke_unknown")
        if player.side != player_side or opponent.side != opponent_side:
            reject(kill, "snapshot_side_mismatch")
            continue
        try:
            player_pose = player.participant()
            opponent_pose = opponent.participant(aim_target=player_pose.position)
        except DemoError as error:
            reject(kill, str(error))
            continue
        except ValidationError:
            reject(kill, "invalid_snapshot_values")
            continue
        if opponent.pitch is None or opponent.yaw is None:
            limitations.append("opponent_aim_inferred_toward_player")
        target = scenarios if lost else wins
        target.append(
            Scenario(
                scenario_id=f"duel-{round_row.round_num}-{kill.tick}-{index}",
                source=Source(
                    demo_sha256=reader.sha256,
                    round_number=round_row.round_num,
                    snapshot_tick=contact - 1,
                    contact_tick=contact,
                    death_tick=kill.tick,
                    parser_name="awpy",
                    parser_version=PARSER_VERSION,
                    rules_version=RULES_VERSION,
                ),
                map=reader.map,
                player=player_pose,
                opponent=opponent_pose,
                limitations=limitations,
            )
        )

    grouped: dict[tuple, list[Scenario]] = defaultdict(list)
    grouped_wins: dict[tuple, list[Scenario]] = defaultdict(list)
    for scenario in scenarios:
        grouped[_group_key(scenario, group_cell_units)].append(scenario)
    for scenario in wins:
        grouped_wins[_group_key(scenario, group_cell_units)].append(scenario)
    ordered = sorted(
        grouped.keys() | grouped_wins.keys(), key=lambda key: (-len(grouped.get(key, [])), key)
    )
    selected = [scenario for key in ordered for scenario in grouped.get(key, [])][:max_scenarios]
    selected_ids = {scenario.scenario_id for scenario in selected}
    groups: list[DuelGroup] = []
    for index, key in enumerate(ordered, start=1):
        losses, victories = grouped.get(key, []), grouped_wins.get(key, [])
        reference = losses[0] if losses else victories[0]
        observations = len(losses) + len(victories)
        groups.append(
            DuelGroup(
                group_id=f"duel-group-{index}",
                observations=observations,
                wins=len(victories),
                losses=len(losses),
                win_rate=len(victories) / observations,
                player_side=reference.player.side,
                player_weapon=reference.player.weapon,
                opponent_weapon=reference.opponent.weapon,
                player_cell=_position_cell(reference.player.position, group_cell_units),
                opponent_cell=_position_cell(reference.opponent.position, group_cell_units),
                context_limitations=reference.limitations,
                selected_scenario_ids=[
                    scenario.scenario_id
                    for scenario in losses
                    if scenario.scenario_id in selected_ids
                ],
            )
        )
    rss = None
    input_blocks = output_blocks = None
    if sys.platform != "win32":
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        input_blocks, output_blocks = usage.ru_inblock, usage.ru_oublock
        if sys.platform != "darwin":
            rss *= 1024
    return AnalysisReport(
        status="candidates_ready" if selected else "no_eligible_duels",
        parser_version=PARSER_VERSION,
        rules_version=RULES_VERSION,
        player_steam_id=steam_id,
        demo_sha256=reader.sha256,
        map=reader.map,
        contact_window_ticks=contact_window_ticks,
        group_cell_units=group_cell_units,
        deaths_considered=sum(str(kill.victim_steamid) == steam_id for kill in kills),
        kills_considered=sum(str(kill.victim_steamid) != steam_id for kill in kills),
        eligible_candidates=len(scenarios),
        eligible_wins=len(wins),
        omitted_by_limit=len(scenarios) - len(selected),
        excluded=sorted(excluded, key=lambda item: item.death_tick),
        excluded_wins=sorted(excluded_wins, key=lambda item: item.death_tick),
        groups=groups,
        scenario_document=ScenarioDocument(schema_version=1, scenarios=selected)
        if selected
        else None,
        limitations=[
            *BASE_LIMITATIONS,
            "ranking_is_loss_frequency_not_win_rate",
            "win_rate_only_covers_filtered_resolved_duels",
            "unresolved_encounters_and_exposure_not_measured",
            "small_samples_do_not_establish_skill",
            "grid_groups_are_heuristic",
            "console_export_not_verified",
        ],
        metrics=Metrics(
            wall_seconds=time.perf_counter() - started,
            cpu_seconds=time.process_time() - cpu_started,
            process_peak_rss_bytes=rss,
            rss_scope="process_lifetime" if rss is not None else "unavailable_on_platform",
            input_block_operations=input_blocks,
            output_block_operations=output_blocks,
            input_bytes=reader.size_bytes,
        ),
    )


def exclusion_counts(report: AnalysisReport) -> dict[str, int]:
    return dict(Counter(item.reason for item in report.excluded))
