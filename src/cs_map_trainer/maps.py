"""Declared map support; Sandbox geometry and client access remain unverified."""

from dataclasses import dataclass
from typing import Literal

Integration = Literal[
    "yprac_hub_mirage_sandbox", "yprac_hub_dust2_sandbox", "yprac_hub_multi_map_sandbox"
]


@dataclass(frozen=True)
class MapSupport:
    label: str
    integration: Integration


SUPPORTED_MAPS = {
    "de_mirage": MapSupport("Mirage", "yprac_hub_mirage_sandbox"),
    "de_dust2": MapSupport("Dust2", "yprac_hub_dust2_sandbox"),
}
SUPPORTED_MAP_NAMES = ", ".join(SUPPORTED_MAPS)


def map_label(name: str | None) -> str:
    support = SUPPORTED_MAPS.get(name) if name else None
    return support.label if support else name or "Map not yet identified"
