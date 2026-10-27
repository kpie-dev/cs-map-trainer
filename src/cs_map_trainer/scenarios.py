"""Versioned domain contract; validation is not proof of game compatibility."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=128)]
Version = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^\S+$")]
SteamID = Annotated[str, Field(pattern=r"^[1-9][0-9]{16}$")]
Tick = Annotated[int, Field(ge=0)]
Coordinate = Annotated[float, Field(allow_inf_nan=False)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Position(ContractModel):
    x: Coordinate
    y: Coordinate
    z: Coordinate


class ViewAngles(ContractModel):
    pitch: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    yaw: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    roll: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class MapIdentity(ContractModel):
    name: Identifier
    game_build: Annotated[int, Field(gt=0)]
    revision: Version


class Source(ContractModel):
    demo_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    round_number: Annotated[int, Field(ge=1)]
    snapshot_tick: Tick
    contact_tick: Tick
    death_tick: Tick
    parser_name: Identifier
    parser_version: Version
    rules_version: Version

    @model_validator(mode="after")
    def validate_tick_order(self) -> Self:
        if not self.snapshot_tick <= self.contact_tick <= self.death_tick:
            raise ValueError("Expected snapshot_tick <= contact_tick <= death_tick")
        if self.snapshot_tick >= self.death_tick:
            raise ValueError("snapshot_tick must precede death_tick")
        return self


class Participant(ContractModel):
    steam_id: SteamID
    side: Literal["T", "CT"]
    position: Position
    view_angles: ViewAngles
    weapon: Identifier


class Scenario(ContractModel):
    scenario_id: Identifier
    source: Source
    map: MapIdentity
    player: Participant
    opponent: Participant
    limitations: list[Identifier]

    @model_validator(mode="after")
    def validate_opponents(self) -> Self:
        if self.player.steam_id == self.opponent.steam_id:
            raise ValueError("Player and opponent must be different participants")
        if self.player.side == self.opponent.side:
            raise ValueError("Player and opponent must be on opposing sides")
        return self


class ScenarioDocument(ContractModel):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    scenarios: Annotated[list[Scenario], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario_id must be unique within the document")
        return self
