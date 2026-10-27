import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from cs_map_trainer.cli import main
from cs_map_trainer.scenarios import MapIdentity

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synthetic-scenarios.json"


def test_valid_document(capsys):
    assert main(["validate-scenarios", str(FIXTURE)]) == 0
    output = capsys.readouterr()
    assert "Valid schema v1: 1 scenario(s)" in output.out
    assert "have not been verified" in output.out
    assert output.err == ""


@pytest.mark.parametrize("content", ['{"schema_version": 2}', "not json", "[]", "\udcff"])
def test_invalid_document(tmp_path, capsys, content):
    path = tmp_path / "invalid.json"
    path.write_bytes(content.encode("utf-8", errors="surrogateescape"))
    assert main(["validate-scenarios", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Invalid scenario document" in output.err


def test_missing_document(tmp_path, capsys):
    assert main(["validate-scenarios", str(tmp_path / "missing.json")]) == 1
    assert "Cannot read" in capsys.readouterr().err


def test_directory_is_not_a_document(tmp_path, capsys):
    assert main(["validate-scenarios", str(tmp_path)]) == 1
    assert "Cannot read" in capsys.readouterr().err


def test_prints_schema(capsys):
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["properties"]["schema_version"]["minimum"] == 1
    assert schema["additionalProperties"] is False


def test_errors_do_not_echo_document_contents(tmp_path, capsys):
    path = tmp_path / "private.json"
    path.write_text('{"private": "do-not-echo-this"}')
    assert main(["validate-scenarios", str(path)]) == 1
    assert "do-not-echo-this" not in capsys.readouterr().err


def test_module_exit_code(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cs_map_trainer.cli", "validate-scenarios", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Cannot read" in result.stderr


def test_missing_command_is_usage_error():
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2


@pytest.mark.parametrize("command", ["players", "analyze", "benchmark"])
def test_missing_demo_is_an_explicit_cli_error(tmp_path, capsys, command):
    args = [command, str(tmp_path / "missing.dem")]
    if command != "players":
        args += ["--steam-id", "76561198000000001"]
    assert main(args) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert "Demo processing failed" in result.err


@pytest.mark.parametrize(
    "options",
    [
        ["--steam-id", "invalid"],
        ["--steam-id", "76561198000000001", "--max-scenarios", "0"],
        ["--steam-id", "76561198000000001", "--contact-window-ticks", "-1"],
    ],
)
def test_analysis_usage_errors_are_rejected_before_parsing(options):
    with pytest.raises(SystemExit) as error:
        main(["analyze", "missing.dem", *options])
    assert error.value.code == 2


@pytest.mark.parametrize("option", ["--runs", "--timeout-seconds"])
def test_invalid_benchmark_options_are_usage_errors(option):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "benchmark",
                "missing.dem",
                "--steam-id",
                "76561198000000001",
                option,
                "0",
            ]
        )
    assert error.value.code == 2


@pytest.fixture
def fake_demo(monkeypatch):
    reader = SimpleNamespace(
        map=MapIdentity(name="de_mirage", game_build=1, revision="test-unverified"),
        players=lambda: pl.DataFrame(
            [{"steamid": 76561198000000001, "name": 'Łukasz; "quit"', "side": "terrorist"}]
        ),
    )
    monkeypatch.setattr("cs_map_trainer.parsing.DemoReader", lambda path: reader)


def test_roster_stdout_is_json_not_console_commands(fake_demo, capsys):
    assert main(["players", "test.dem"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["players"][0]["name"] == 'Łukasz; "quit"'
    assert output.err == ""


def test_roster_output_file(fake_demo, tmp_path, capsys):
    output = tmp_path / "roster.json"
    assert main(["players", "test.dem", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["players"][0]["steam_id"] == "76561198000000001"
    assert capsys.readouterr().out == ""


def test_existing_output_is_never_overwritten(fake_demo, tmp_path, capsys):
    output = tmp_path / "roster.json"
    output.write_text("existing")
    assert main(["players", "test.dem", "--output", str(output)]) == 1
    assert output.read_text() == "existing"
    assert "Demo processing failed" in capsys.readouterr().err
