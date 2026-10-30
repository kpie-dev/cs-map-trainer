"""Versioned local scoreboard metrics, independent of training-duel eligibility.

The public Rating 2.0 regression is documented at
https://dave.xn--tckwe/posts/reverse-engineering-hltv-rating/ .
It is not the proprietary HLTV calculation (or Rating 3.0).
"""

import math
from collections import defaultdict
from typing import Literal, Self

import polars as pl
from pydantic import ConfigDict, Field, model_validator

from cs_map_trainer.analysis import SIDES, RoundRow, _round_for
from cs_map_trainer.scenarios import ContractModel, SteamID

METRIC_VERSION = "live-scoreboard-v1"
TRADE_SECONDS = 5


class MatchStatistics(ContractModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    metric_version: Literal["live-scoreboard-v1"] = METRIC_VERSION
    steam_id: SteamID
    rounds_played: int = Field(ge=0)
    kills: int | None = Field(default=None, ge=0)
    deaths: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    rating_assists: int | None = Field(default=None, ge=0)
    damage_hp: int | None = Field(default=None, ge=0)
    headshot_kills: int | None = Field(default=None, ge=0)
    adr: float | None = Field(default=None, ge=0)
    hs_percent: float | None = Field(default=None, ge=0, le=100)
    kpr: float | None = Field(default=None, ge=0)
    dpr: float | None = Field(default=None, ge=0)
    apr: float | None = Field(default=None, ge=0)
    kast: float | None = Field(default=None, ge=0, le=100)
    impact: float | None = None
    estimated_rating_2: float | None = None
    rating_label: Literal["Estimated Rating 2.0"] = "Estimated Rating 2.0"
    trade_window_seconds: Literal[5] = TRADE_SECONDS
    unavailable: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(
        default_factory=lambda: [
            "local_approximation_not_official_hltv_rating_2_or_3",
            "live_rounds_from_awpy_exclude_knife_and_warmup_include_overtime",
            "participation_requires_alive_playing_side_at_freeze_end",
            "deaths_include_world_suicide_and_teamkill_victims",
            "kills_exclude_world_suicide_and_teamkills_no_teamkill_penalty",
            "scoreboard_assists_include_native_damage_and_flash_assists",
            "rating_assists_require_40_enemy_hp_or_native_flash_assist_per_kill",
            "kast_uses_rating_assists_and_same_round_teammate_trade_within_5_seconds",
            "survival_inferred_from_no_death_in_participating_live_round",
            "post_round_events_excluded",
        ]
    )

    @model_validator(mode="after")
    def explicit_unavailable_metrics(self) -> Self:
        for field in (
            "kills",
            "deaths",
            "assists",
            "rating_assists",
            "damage_hp",
            "headshot_kills",
            "adr",
            "hs_percent",
            "kpr",
            "dpr",
            "apr",
            "kast",
            "impact",
            "estimated_rating_2",
        ):
            if getattr(self, field) is None and not self.unavailable.get(field):
                raise ValueError(f"Unavailable metric {field} requires an explicit reason")
        return self


def live_rounds(rounds: list[RoundRow]) -> list[RoundRow]:
    return [
        row
        for row in rounds
        if not row.is_knife_round
        and not row.is_warmup
        and row.freeze_end_tick is not None
        and row.end_tick is not None
    ]


def _enemy(row: dict) -> bool:
    return (
        row.get("attacker_steamid") not in (None, 0, row.get("victim_steamid"))
        and row.get("attacker_side") in SIDES
        and row.get("victim_side") in SIDES
        and row["attacker_side"] != row["victim_side"]
    )


def match_statistics(
    steam_id: str,
    rounds: list[RoundRow],
    kills: pl.DataFrame,
    damages: pl.DataFrame,
    snapshots: pl.DataFrame,
    *,
    tickrate: float | None,
) -> MatchStatistics:
    player = int(steam_id)
    rounds = live_rounds(rounds)
    snapshot_rows = snapshots.to_dicts()
    participation = {
        row.round_num
        for row in rounds
        if any(
            snap.get("tick") == row.freeze_end_tick
            and snap.get("steamid") == player
            and snap.get("side") in SIDES
            and (snap.get("health") or 0) > 0
            for snap in snapshot_rows
        )
    }
    result = MatchStatistics.model_construct(steam_id=steam_id, rounds_played=len(participation))
    unavailable = result.unavailable
    kill_columns = set(kills.columns)
    damage_columns = set(damages.columns)
    kill_ok = {
        "tick",
        "attacker_steamid",
        "victim_steamid",
        "attacker_side",
        "victim_side",
    } <= kill_columns
    damage_ok = {
        "tick",
        "attacker_steamid",
        "victim_steamid",
        "attacker_side",
        "victim_side",
        "dmg_health",
        "health_pre",
    } <= damage_columns
    kill_rows = sorted(
        [row for row in kills.to_dicts() if _round_for(row.get("tick", -1), rounds)],
        key=lambda row: row["tick"],
    )
    damage_rows = [row for row in damages.to_dicts() if _round_for(row.get("tick", -1), rounds)]
    # Unknown sides cannot safely be interpreted as either a teamkill or an enemy kill.
    kill_ok &= all(
        row.get("victim_side") in SIDES
        and (not row.get("attacker_steamid") or row.get("attacker_side") in SIDES)
        for row in kill_rows
    )
    damage_ok &= all(
        row.get("dmg_health") is not None
        and row.get("health_pre") is not None
        and row.get("victim_side") in SIDES
        and (not row.get("attacker_steamid") or row.get("attacker_side") in SIDES)
        for row in damage_rows
    )
    enemy_kills = [row for row in kill_rows if _enemy(row)]
    scored = [row for row in enemy_kills if row["attacker_steamid"] == player]
    deaths = [row for row in kill_rows if row.get("victim_steamid") == player]
    if kill_ok:
        result.kills, result.deaths = len(scored), len(deaths)
    else:
        unavailable.update(kills="missing_kill_identity_or_side", deaths="missing_kill_fields")
    assist_ok = kill_ok and {"assister_steamid", "assister_side", "assist_flash"} <= kill_columns
    assist_ok &= all(row.get("assist_flash") is not None for row in enemy_kills)
    assist_ok &= all(
        not row.get("assister_steamid") or row.get("assister_side") in SIDES for row in enemy_kills
    )
    if assist_ok:
        result.assists = sum(
            row.get("assister_steamid") == player
            and row.get("assister_side") == row["attacker_side"]
            and player != row["attacker_steamid"]
            for row in enemy_kills
        )
    else:
        unavailable["assists"] = "missing_native_assist_fields"
    if (
        kill_ok
        and "headshot" in kill_columns
        and all(row.get("headshot") is not None for row in scored)
    ):
        result.headshot_kills = sum(row["headshot"] for row in scored)
        if result.kills:
            result.hs_percent = 100 * result.headshot_kills / result.kills
        else:
            unavailable["hs_percent"] = "no_enemy_kills"
    else:
        unavailable["headshot_kills"] = unavailable["hs_percent"] = "missing_headshot_fields"
    if damage_ok:
        result.damage_hp = sum(
            max(0, min(row["dmg_health"], row["health_pre"]))
            for row in damage_rows
            if _enemy(row) and row["attacker_steamid"] == player
        )
    else:
        unavailable["damage_hp"] = "missing_enemy_hp_damage_or_pre_hit_health"
    assist_rounds = set()
    if damage_ok and assist_ok:
        result.rating_assists = 0
        for kill in enemy_kills:
            round_row = _round_for(kill["tick"], rounds)
            contributions = defaultdict(int)
            for damage in damage_rows:
                if (
                    _enemy(damage)
                    and damage["victim_steamid"] == kill["victim_steamid"]
                    and round_row.freeze_end_tick <= damage["tick"] <= kill["tick"]
                    and damage["attacker_side"] == kill["attacker_side"]
                ):
                    contributions[damage["attacker_steamid"]] += max(
                        0, min(damage["dmg_health"], damage["health_pre"])
                    )
            assisted = contributions[player] >= 40 or (
                kill.get("assister_steamid") == player
                and kill.get("assist_flash") is True
                and kill.get("assister_side") == kill["attacker_side"]
            )
            if assisted and player not in (kill["attacker_steamid"], kill["victim_steamid"]):
                result.rating_assists += 1
                assist_rounds.add(round_row.round_num)
    else:
        unavailable["rating_assists"] = "requires_hp_damage_and_native_flash_assists"
    event_rounds = {
        _round_for(row["tick"], rounds).round_num
        for row in [*kill_rows, *damage_rows]
        if player
        in (row.get("attacker_steamid"), row.get("victim_steamid"), row.get("assister_steamid"))
    }
    if not participation or event_rounds - participation:
        reason = (
            "no_participating_live_rounds"
            if not participation
            else "events_without_round_participation_snapshot"
        )
        for field in ("adr", "kpr", "dpr", "apr", "kast", "estimated_rating_2", "impact"):
            unavailable[field] = reason
        return MatchStatistics.model_validate(result.model_dump())
    for metric, source in (
        ("adr", "damage_hp"),
        ("kpr", "kills"),
        ("dpr", "deaths"),
        ("apr", "rating_assists"),
    ):
        value = getattr(result, source)
        if value is not None:
            setattr(result, metric, value / len(participation))
        else:
            unavailable[metric] = f"requires_{source}"
    if (
        kill_ok
        and result.rating_assists is not None
        and tickrate
        and math.isfinite(tickrate)
        and tickrate > 0
    ):
        credited = set(assist_rounds)
        for row in rounds:
            if row.round_num not in participation:
                continue
            local = [kill for kill in kill_rows if _round_for(kill["tick"], [row])]
            own_deaths = [kill for kill in local if kill["victim_steamid"] == player]
            if not own_deaths or any(
                _enemy(kill) and kill["attacker_steamid"] == player for kill in local
            ):
                credited.add(row.round_num)
            for index, death in enumerate(local):
                if death["victim_steamid"] != player:
                    continue
                if not _enemy(death):
                    continue
                if any(
                    _enemy(trade)
                    and trade["victim_steamid"] == death["attacker_steamid"]
                    and trade["attacker_side"] == death["victim_side"]
                    and trade["attacker_steamid"] != player
                    and 0 <= trade["tick"] - death["tick"] <= TRADE_SECONDS * tickrate
                    for trade in local[index + 1 :]
                ):
                    credited.add(row.round_num)
        result.kast = 100 * len(credited) / len(participation)
    else:
        unavailable["kast"] = "requires_kills_rating_assists_and_verified_tickrate"
    if result.kpr is not None and result.apr is not None:
        result.impact = 2.13 * result.kpr + 0.42 * result.apr - 0.41
    else:
        unavailable["impact"] = "requires_kpr_and_apr"
    if all(getattr(result, name) is not None for name in ("kast", "kpr", "dpr", "impact", "adr")):
        result.estimated_rating_2 = (
            0.0073 * result.kast
            + 0.3591 * result.kpr
            - 0.5329 * result.dpr
            + 0.2372 * result.impact
            + 0.0032 * result.adr
            + 0.1587
        )
    else:
        unavailable["estimated_rating_2"] = "incomplete_rating_components"
    return MatchStatistics.model_validate(result.model_dump())
