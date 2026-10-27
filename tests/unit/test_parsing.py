import pytest

from cs_map_trainer.parsing import DemoError, DemoReader


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
