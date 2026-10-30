import pytest

from cs_map_trainer.callouts import format_place_name


@pytest.mark.parametrize(
    "native, label",
    [
        ("BombsiteA", "A Site"),
        ("BombsiteB", "B Site"),
        ("TSpawn", "T Spawn"),
        ("CTSpawn", "CT Spawn"),
        ("TopofMid", "Top Mid"),
        ("MidDoors", "Mid Doors"),
        ("UpperTunnel", "Upper Tunnels"),
        ("LowerTunnel", "Lower Tunnels"),
        ("LongA", "A Long"),
        ("TunnelStairs", "Tunnel Stairs"),
        ("ExtendedA", "Extended A"),
        ("UnderA", "Under A"),
        ("FuturePlace", "Future Place"),
        ("already readable", "already readable"),
        (None, None),
    ],
)
@pytest.mark.parametrize("map_name", ["de_dust2", "de_mirage"])
def test_native_place_display_labels(map_name, native, label):
    assert format_place_name(map_name, native) == label


@pytest.mark.parametrize(
    "native, mirage, dust2",
    [
        ("TRamp", "A Ramp", "T Ramp"),
        ("SnipersNest", "Window", "Snipers Nest"),
        ("Shop", "Market", "Shop"),
        ("Truck", "Van", "Truck"),
        ("Apartments", "B Apartments", "Apartments"),
    ],
)
def test_community_aliases_are_map_specific(native, mirage, dust2):
    assert format_place_name("de_mirage", native) == mirage
    assert format_place_name("de_dust2", native) == dust2
