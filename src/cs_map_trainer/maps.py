"""Declared map support; Sandbox geometry and client access remain unverified."""

from dataclasses import dataclass
from typing import Literal

Integration = Literal[
    "yprac_hub_mirage_sandbox",
    "yprac_hub_dust2_sandbox",
    "yprac_hub_cache_sandbox",
    "yprac_hub_inferno_sandbox",
    "yprac_hub_nuke_sandbox",
    "yprac_hub_ancient_sandbox",
    "yprac_hub_anubis_sandbox",
    "yprac_hub_multi_map_sandbox",
]


@dataclass(frozen=True)
class MapSupport:
    label: str
    integration: Integration


SUPPORTED_MAPS = {
    "de_mirage": MapSupport("Mirage", "yprac_hub_mirage_sandbox"),
    "de_dust2": MapSupport("Dust2", "yprac_hub_dust2_sandbox"),
    "de_cache": MapSupport("Cache", "yprac_hub_cache_sandbox"),
    "de_inferno": MapSupport("Inferno", "yprac_hub_inferno_sandbox"),
    "de_nuke": MapSupport("Nuke", "yprac_hub_nuke_sandbox"),
    "de_ancient": MapSupport("Ancient", "yprac_hub_ancient_sandbox"),
    "de_anubis": MapSupport("Anubis", "yprac_hub_anubis_sandbox"),
}
SUPPORTED_MAP_NAMES = ", ".join(SUPPORTED_MAPS)
SUPPORTED_MAP_LABELS = ", ".join(support.label for support in SUPPORTED_MAPS.values())


def map_label(name: str | None) -> str:
    support = SUPPORTED_MAPS.get(name) if name else None
    return support.label if support else name or "Map not yet identified"
