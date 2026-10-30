"""Adapter for the pinned Awpy API. No chat, voice or map assets are requested."""

import hashlib
from pathlib import Path

import polars as pl
from awpy import Demo, InvalidDemoError
from pydantic import ValidationError

from cs_map_trainer.maps import SUPPORTED_MAP_NAMES, SUPPORTED_MAPS
from cs_map_trainer.scenarios import MapIdentity

PARSER_VERSION = "3.1.1"
MAX_DEMO_BYTES = 1024**3


class DemoError(ValueError):
    """An invalid, unsupported or incomplete demo input."""


class DemoReader:
    def __init__(self, path: Path):
        if not path.is_file():
            raise DemoError("Demo must be a regular .dem file")
        if path.suffix.lower() != ".dem":
            raise DemoError("Expected an uncompressed .dem file")
        self.size_bytes = path.stat().st_size
        if self.size_bytes > MAX_DEMO_BYTES:
            raise DemoError("Demo exceeds the current 1 GiB input limit")
        with path.open("rb") as handle:
            if handle.read(8) != b"PBDEMS2\x00":
                raise DemoError("Not a CS2 demo: expected PBDEMS2 header")
            handle.seek(0)
            self.sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
        try:
            self.demo = Demo(path)
        except InvalidDemoError as error:
            raise DemoError(f"Cannot open CS2 demo: {error}") from error
        header = self.demo.header
        try:
            build = header["build_num"]
            self.map = MapIdentity(
                name=header["map_name"],
                game_build=build,
                revision=f"unverified-demo-build-{build}",
            )
        except (KeyError, ValidationError) as error:
            raise DemoError("Demo is missing a valid map name or game build") from error
        if self.map.name not in SUPPORTED_MAPS:
            raise DemoError(f"Supported analysis maps: {SUPPORTED_MAP_NAMES}")

    def players(self) -> pl.DataFrame:
        return self.demo.players

    def combat(self) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        self.demo.load("rounds", "kills", "damages")
        return self.demo.rounds, self.demo.kills, self.demo.damages

    def snapshots(self, ticks: list[int]) -> pl.DataFrame:
        return self.demo.snapshots(ticks=ticks)
