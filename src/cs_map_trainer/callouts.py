"""Display labels for native demo place names; no position-based guesses."""

import re

LABELS = {
    "BombsiteA": "A Site",
    "BombsiteB": "B Site",
    "TSpawn": "T Spawn",
    "CTSpawn": "CT Spawn",
    "TopofMid": "Top Mid",
    "Middle": "Mid",
    "TRamp": "T Ramp",
    "ARamp": "A Ramp",
    "LongA": "A Long",
    "BDoors": "B Doors",
    "OutsideTunnel": "Outside Tunnels",
    "UpperTunnel": "Upper Tunnels",
    "LowerTunnel": "Lower Tunnels",
    "ExtendedA": "Extended A",
    "UnderA": "Under A",
}
MIRAGE_LABELS = {
    "Apartments": "B Apartments",
    "SnipersNest": "Window",
    "Shop": "Market",
    "Truck": "Van",
    "PalaceInterior": "Palace",
    "Ladder": "Ladder Room",
    "TRamp": "A Ramp",
}


def format_place_name(map_name: str, name: str | None) -> str | None:
    if name is None:
        return None
    if map_name == "de_mirage" and name in MIRAGE_LABELS:
        return MIRAGE_LABELS[name]
    return LABELS.get(name, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name))
