from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from cs_map_trainer.maps import SUPPORTED_MAP_NAMES, SUPPORTED_MAPS
from cs_map_trainer.parsing import DemoError, DemoReader


def test_supported_maps_match_the_product_scope():
    assert {name: support.label for name, support in SUPPORTED_MAPS.items()} == {
        "de_cache": "Cache",
        "de_dust2": "Dust2",
        "de_mirage": "Mirage",
        "de_inferno": "Inferno",
        "de_nuke": "Nuke",
        "de_ancient": "Ancient",
        "de_anubis": "Anubis",
    }
    for name, support in SUPPORTED_MAPS.items():
        assert support.integration == f"yprac_hub_{name.removeprefix('de_')}_sandbox"


def test_missing_input(tmp_path):
    with pytest.raises(DemoError, match="regular"):
        DemoReader(tmp_path / "missing.dem")


def test_directory_input(tmp_path):
    with pytest.raises(DemoError, match="regular"):
        DemoReader(tmp_path)


@pytest.mark.parametrize("content", [b"", b"HL2DEMO\x00", b"not a demo"])
def test_rejects_non_cs2_demos(tmp_path, content):
    path = tmp_path / "invalid.dem"
    path.write_bytes(content)
    with pytest.raises(DemoError, match="PBDEMS2"):
        DemoReader(path)


def test_rejects_archives(tmp_path):
    path = tmp_path / "demo.dem.gz"
    path.write_bytes(b"PBDEMS2\x00")
    with pytest.raises(DemoError, match="uncompressed"):
        DemoReader(path)


def test_native_parser_rejects_truncated_file(tmp_path):
    path = tmp_path / "truncated.dem"
    path.write_bytes(b"PBDEMS2\x00")
    with pytest.raises(DemoError, match="Cannot open"):
        DemoReader(path)


def test_size_limit_is_enforced_before_decoding(tmp_path, monkeypatch):
    path = tmp_path / "large.dem"
    path.write_bytes(b"PBDEMS2\x00")
    monkeypatch.setattr("cs_map_trainer.parsing.MAX_DEMO_BYTES", 1)
    with pytest.raises(DemoError, match="limit"):
        DemoReader(path)


@pytest.mark.parametrize("map_name", [*SUPPORTED_MAPS, "de_train", "de_overpass", "de_unknown"])
def test_map_support_comes_from_demo_header(tmp_path, monkeypatch, map_name):
    path = tmp_path / "misleading-dust2-name.dem"
    path.write_bytes(b"PBDEMS2\x00")
    monkeypatch.setattr(
        "cs_map_trainer.parsing.Demo",
        lambda path: SimpleNamespace(header={"map_name": map_name, "build_num": 123}),
    )
    if map_name in SUPPORTED_MAPS:
        reader = DemoReader(path)
        assert reader.map.name == map_name
        assert reader.map.game_build == 123
        assert reader.map.revision == "unverified-demo-build-123"
    else:
        with pytest.raises(DemoError, match=SUPPORTED_MAP_NAMES):
            DemoReader(path)


def reader_with_native_data(tmp_path, monkeypatch, frame):
    native = SimpleNamespace(
        header={"map_name": "de_dust2", "build_num": 123}, ticks=Mock(return_value=frame)
    )
    path = tmp_path / "native.dem"
    path.write_bytes(b"PBDEMS2\x00")
    monkeypatch.setattr("cs_map_trainer.parsing.Demo", lambda path: native)
    return DemoReader(path), native


def test_locations_use_raw_awpy_property_and_exact_ticks_only(tmp_path, monkeypatch):
    reader, native = reader_with_native_data(
        tmp_path,
        monkeypatch,
        pl.DataFrame(
            {
                "tick": [98, 99, 99, 120],
                "steamid": [1, 1, 2, 1],
                "m_szLastPlaceName": ["Previous", "BombsiteA", "CTSpawn", "Death"],
                "unrequested": [0, 0, 0, 0],
            }
        ),
    )
    frame = reader.locations([99])
    native.ticks.assert_called_once_with(props=["m_szLastPlaceName"], players_only=True)
    assert frame.to_dicts() == [
        {"tick": 99, "steamid": 1, "last_place_name": "BombsiteA"},
        {"tick": 99, "steamid": 2, "last_place_name": "CTSpawn"},
    ]


def test_empty_location_request_does_not_scan_the_demo(tmp_path, monkeypatch):
    reader, native = reader_with_native_data(tmp_path, monkeypatch, pl.DataFrame())
    assert reader.locations([]).columns == ["tick", "steamid", "last_place_name"]
    native.ticks.assert_not_called()


@pytest.mark.parametrize("missing", ["tick", "steamid", "m_szLastPlaceName"])
def test_missing_native_location_columns_fail_explicitly(tmp_path, monkeypatch, missing):
    frame = pl.DataFrame({"tick": [99], "steamid": [1], "m_szLastPlaceName": ["CTSpawn"]})
    reader, _ = reader_with_native_data(tmp_path, monkeypatch, frame.drop(missing))
    with pytest.raises(DemoError, match="missing required columns"):
        reader.locations([99])


@pytest.mark.parametrize("name", [None, ""])
def test_absent_native_values_remain_absent_instead_of_guessing(tmp_path, monkeypatch, name):
    frame = pl.DataFrame(
        {"tick": [99], "steamid": [1], "m_szLastPlaceName": [name]},
        schema={"tick": pl.Int64, "steamid": pl.UInt64, "m_szLastPlaceName": pl.String},
    )
    reader, _ = reader_with_native_data(tmp_path, monkeypatch, frame)
    assert reader.locations([99])["last_place_name"].to_list() == [name]


@pytest.mark.parametrize(
    "rate,expected", [(64.0, 64.0), (128, 128), (None, None), (0, None), (float("inf"), None)]
)
def test_native_tick_rate_is_verified_not_assumed(tmp_path, monkeypatch, rate, expected):
    reader, native = reader_with_native_data(tmp_path, monkeypatch, pl.DataFrame())
    native.tick_rate = rate
    assert reader.tick_rate == expected
