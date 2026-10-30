import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import polars as pl
import pytest

from cs_map_trainer.cli import main
from cs_map_trainer.exporting import export_scenario
from cs_map_trainer.maps import SUPPORTED_MAPS
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


@pytest.fixture(params=SUPPORTED_MAPS)
def fake_demo(monkeypatch, request):
    reader = SimpleNamespace(
        map=MapIdentity(name=request.param, game_build=1, revision="test-unverified"),
        players=lambda: pl.DataFrame(
            [{"steamid": 76561198000000001, "name": 'Łukasz; "quit"', "side": "terrorist"}]
        ),
    )
    monkeypatch.setattr("cs_map_trainer.parsing.DemoReader", lambda path: reader)
    return reader


def test_roster_stdout_is_json_not_console_commands(fake_demo, capsys):
    assert main(["players", "test.dem"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["players"][0]["name"] == 'Łukasz; "quit"'
    assert json.loads(output.out)["map"] == fake_demo.map.model_dump()
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


@pytest.fixture
def training_input(tmp_path, training_document):
    path = tmp_path / "scenarios.json"
    path.write_text(training_document.model_dump_json(), encoding="utf-8")
    return path


def test_export_stdout_is_exactly_one_console_line(training_input, training_document, capsys):
    reference = training_document.scenarios[0]
    assert (
        main(["export-scenario", str(training_input), "--scenario-id", reference.scenario_id]) == 0
    )
    result = capsys.readouterr()
    assert result.out == export_scenario(reference).console_line + "\n"
    assert len(result.out.splitlines()) == 1
    assert "unverified_in_game" in result.err
    assert "player index 2 AND pawn entity index 2" in result.err


def test_export_optional_cfg_file(training_input, training_document, tmp_path, capsys):
    reference = training_document.scenarios[0]
    output = tmp_path / "training.cfg"
    assert (
        main(
            [
                "export-scenario",
                str(training_input),
                "--scenario-id",
                reference.scenario_id,
                "--cfg",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.read_text() == export_scenario(reference).cfg
    assert capsys.readouterr().out == ""


def test_pack_cli_writes_archive_not_stdout(training_input, tmp_path, capsys):
    output = tmp_path / "pack.zip"
    assert (
        main(
            [
                "build-pack",
                str(training_input),
                "--include",
                "synthetic-duel-1",
                "--include-cfg",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    with ZipFile(BytesIO(output.read_bytes())) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["selected_scenario_ids"] == ["synthetic-duel-1"]
        assert manifest["compatibility"] == "unverified_in_game"
        assert "cfg/scenario-0001.cfg" in archive.namelist()
    result = capsys.readouterr()
    assert result.out == ""
    assert "unverified_in_game" in result.err


def test_training_cli_accepts_report(training_report, tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(training_report.model_dump_json())
    assert main(["export-scenario", str(path), "--scenario-id", "synthetic-duel-1"]) == 0
    assert "setpos_player 2" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["export-scenario", "build-pack"])
@pytest.mark.parametrize("kind", ["missing", "invalid", "no-candidates", "synthetic"])
def test_training_input_errors_do_not_create_output(
    tmp_path, capsys, training_report, command, kind
):
    path = tmp_path / "input.json"
    if kind == "invalid":
        path.write_text('{"private": "do-not-echo-this"}')
    elif kind == "no-candidates":
        training_report.scenario_document = None
        training_report.status = "no_eligible_duels"
        path.write_text(training_report.model_dump_json())
    elif kind == "synthetic":
        path = FIXTURE
    output = tmp_path / "artifact"
    args = [command, str(path), "--output", str(output)]
    if command == "export-scenario":
        args += ["--scenario-id", "synthetic-duel-1"]
    assert main(args) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert result.err
    assert "do-not-echo-this" not in result.err
    assert "Experimental export:" not in result.err
    assert not output.exists()


@pytest.mark.parametrize("command", ["export-scenario", "build-pack"])
def test_training_never_overwrites_existing_output(training_input, tmp_path, capsys, command):
    output = tmp_path / "artifact"
    output.write_bytes(b"existing")
    args = [command, str(training_input), "--output", str(output)]
    if command == "export-scenario":
        args += ["--scenario-id", "synthetic-duel-1"]
    assert main(args) == 1
    assert output.read_bytes() == b"existing"
    assert "Training export failed" in capsys.readouterr().err
    assert not list(tmp_path.glob(".cmt-*"))


@pytest.mark.parametrize(
    "options",
    [
        ["--include", "missing"],
        ["--include", "synthetic-duel-1", "--include", "synthetic-duel-1"],
        ["--reject", "synthetic-duel-1"],
        ["--include", "synthetic-duel-1", "--reject", "synthetic-duel-1"],
    ],
)
def test_cli_selection_errors(training_input, tmp_path, capsys, options):
    output = tmp_path / "pack.zip"
    assert main(["build-pack", str(training_input), "--output", str(output), *options]) == 1
    assert capsys.readouterr().out == ""
    assert not output.exists()


@pytest.mark.parametrize(
    "args",
    [
        ["build-pack", "input.json"],
        ["export-scenario", "input.json"],
    ],
)
def test_training_required_arguments_are_usage_errors(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_pack_filesystem_failure_is_explicit(training_input, tmp_path, capsys):
    assert (
        main(
            ["build-pack", str(training_input), "--output", str(tmp_path / "missing" / "pack.zip")]
        )
        == 1
    )
    result = capsys.readouterr()
    assert result.out == ""
    assert "Training export failed" in result.err
