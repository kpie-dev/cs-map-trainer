"""One native extraction shared by up to five independent player analyses."""

import time
from typing import Literal, Self

import polars as pl
from pydantic import Field, model_validator

from cs_map_trainer.analysis import (
    AnalysisReport,
    DamageRow,
    KillRow,
    Reader,
    RoundRow,
    SnapshotRow,
    _analyze,
    _candidates,
    _metrics,
    _scenario_locations,
    _validate_parameters,
    roster,
)
from cs_map_trainer.match_statistics import MatchStatistics, live_rounds, match_statistics
from cs_map_trainer.parsing import DemoError
from cs_map_trainer.scenarios import ContractModel, SteamID


class TeamAnalysisRequest(ContractModel):
    steam_ids: list[SteamID] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_players(self) -> Self:
        if len(set(self.steam_ids)) != len(self.steam_ids):
            raise ValueError("Team SteamIDs must be unique")
        return self


class TeamPlayerResult(ContractModel):
    steam_id: SteamID
    status: Literal["ready", "missing"]
    report: AnalysisReport | None
    statistics: MatchStatistics | None

    @model_validator(mode="after")
    def consistent_player(self) -> Self:
        if self.status == "missing":
            if self.report is not None or self.statistics is not None:
                raise ValueError("Missing players cannot have analysis data")
        elif (
            self.report is None
            or self.statistics is None
            or self.report.player_steam_id != self.steam_id
            or self.statistics.steam_id != self.steam_id
        ):
            raise ValueError("Ready results require matching report and statistics")
        return self


class TeamAnalysisResult(ContractModel):
    players: list[TeamPlayerResult] = Field(min_length=1, max_length=5)
    error: Literal["team_players_not_in_demo"] | None = None

    @model_validator(mode="after")
    def consistent_team(self) -> Self:
        ids = [player.steam_id for player in self.players]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate team result")
        ready = [player for player in self.players if player.status == "ready"]
        if bool(ready) == bool(self.error):
            raise ValueError("No present players requires team_players_not_in_demo")
        identities = {
            (player.report.demo_sha256, player.report.map.model_dump_json()) for player in ready
        }
        if len(identities) > 1:
            raise ValueError("All team results must come from the same demo and map")
        return self


TeamAnalysis = TeamAnalysisResult


def analyze_team(
    reader: Reader,
    steam_ids: list[str],
    *,
    max_scenarios: int = 10,
    contact_window_ticks: int = 128,
    group_cell_units: float = 256.0,
) -> TeamAnalysisResult:
    started = time.perf_counter(), time.process_time()
    request = TeamAnalysisRequest(steam_ids=steam_ids)
    _validate_parameters(max_scenarios, contact_window_ticks, group_cell_units)
    present = {player.steam_id for player in roster(reader).players} & set(request.steam_ids)
    if not present:
        return TeamAnalysisResult(
            players=[
                TeamPlayerResult(steam_id=sid, status="missing", report=None, statistics=None)
                for sid in request.steam_ids
            ],
            error="team_players_not_in_demo",
        )
    rounds_frame, kills_frame, damages_frame = reader.combat()
    rounds = [RoundRow.model_validate(row) for row in rounds_frame.to_dicts()]
    kills = [KillRow.model_validate(row) for row in kills_frame.to_dicts()]
    damages = [DamageRow.model_validate(row) for row in damages_frame.to_dicts()]
    prepared = rounds, kills, damages
    ticks = {row.freeze_end_tick for row in live_rounds(rounds)}
    needed = {(tick, int(steam_id)) for tick in ticks for steam_id in present}
    for steam_id in present:
        player_kills = [
            kill
            for kill in kills
            if steam_id in (str(kill.victim_steamid), str(kill.attacker_steamid))
        ]
        for kill, _, contact in _candidates(
            rounds, player_kills, damages, contact_window_ticks, lambda *_: None
        ):
            ticks.add(contact - 1)
            needed.update(
                (contact - 1, sid) for sid in (kill.attacker_steamid, kill.victim_steamid)
            )
    snapshots = reader.snapshots(sorted(ticks)) if ticks else pl.DataFrame()
    seen = set()
    for row in snapshots.to_dicts():
        if (row.get("tick"), row.get("steamid")) not in needed:
            continue
        snapshot = SnapshotRow.model_validate(row)
        key = snapshot.tick, snapshot.steamid
        if key in seen:
            raise DemoError("Ambiguous duplicate player snapshot at the same tick")
        seen.add(key)
    reports = {
        steam_id: _analyze(
            reader,
            steam_id,
            max_scenarios=max_scenarios,
            contact_window_ticks=contact_window_ticks,
            group_cell_units=group_cell_units,
            prepared=prepared,
            snapshot_frame=snapshots,
            defer_locations=True,
            started=started,
        )
        for steam_id in request.steam_ids
        if steam_id in present
    }
    location_ticks = sorted(
        {
            scenario.source.snapshot_tick
            for report in reports.values()
            if report.scenario_document
            for scenario in report.scenario_document.scenarios
        }
    )
    locations = reader.locations(location_ticks) if location_ticks else pl.DataFrame()
    for report in reports.values():
        if report.scenario_document:
            report.scenario_locations = _scenario_locations(
                reader,
                report.scenario_document.scenarios,
                locations,
            )
    result = TeamAnalysisResult(
        players=[
            TeamPlayerResult(
                steam_id=steam_id,
                status="ready" if steam_id in present else "missing",
                report=reports.get(steam_id),
                statistics=match_statistics(
                    steam_id,
                    rounds,
                    kills_frame,
                    damages_frame,
                    snapshots,
                    tickrate=getattr(reader, "tick_rate", None),
                )
                if steam_id in present
                else None,
            )
            for steam_id in request.steam_ids
        ]
    )
    metrics = _metrics(reader, started)
    for player in result.players:
        if player.report is not None:
            player.report.metrics = metrics.model_copy()
    return result
