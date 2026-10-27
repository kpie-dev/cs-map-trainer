import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cs_map_trainer.analysis import AnalysisReport, Metrics
from cs_map_trainer.benchmark import benchmark
from cs_map_trainer.parsing import DemoError
from cs_map_trainer.scenarios import MapIdentity


@pytest.fixture
def report():
    return AnalysisReport(
        status="no_eligible_duels",
        parser_version="3.1.1",
        rules_version="damage-window-v2",
        player_steam_id="76561198000000001",
        demo_sha256="0" * 64,
        map=MapIdentity(name="de_mirage", game_build=1, revision="test-unverified"),
        contact_window_ticks=128,
        group_cell_units=256.0,
        deaths_considered=0,
        kills_considered=0,
        eligible_candidates=0,
        eligible_wins=0,
        omitted_by_limit=0,
        excluded=[],
        excluded_wins=[],
        groups=[],
        scenario_document=None,
        limitations=[],
        metrics=Metrics(
            wall_seconds=1.0,
            cpu_seconds=0.5,
            process_peak_rss_bytes=1024,
            rss_scope="process_lifetime",
            input_bytes=100,
        ),
    )


def test_benchmark_launches_separate_cli_processes_and_preserves_metrics(monkeypatch, report):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        value = report.model_copy(deep=True)
        value.metrics.cpu_seconds = len(calls) * 0.5
        return SimpleNamespace(returncode=0, stdout=value.model_dump_json().encode(), stderr=b"")

    monkeypatch.setattr("cs_map_trainer.benchmark.subprocess.run", run)
    result = benchmark(Path("demo with spaces.dem"), report.player_steam_id, runs=2)
    assert len(calls) == 2
    assert calls[0][0][1:5] == ["-m", "cs_map_trainer.cli", "analyze", "demo with spaces.dem"]
    assert calls[0][1] == {"capture_output": True, "timeout": 300, "check": False}
    assert [run.phase for run in result.runs] == ["first_observed", "repeat"]
    assert [run.metrics.cpu_seconds for run in result.runs] == [0.5, 1.0]
    assert all(run.output_bytes > 0 and run.process_wall_seconds >= 0 for run in result.runs)
    assert result.status == "no_eligible_duels"
    assert "first_observed_is_not_guaranteed_cold" in result.limitations


def test_benchmark_fails_on_changed_analysis_results(monkeypatch, report):
    calls = 0

    def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        value = report.model_copy(deep=True)
        value.demo_sha256 = str(calls) * 64
        return SimpleNamespace(returncode=0, stdout=value.model_dump_json().encode(), stderr=b"")

    monkeypatch.setattr("cs_map_trainer.benchmark.subprocess.run", run)
    with pytest.raises(DemoError, match="changed the analysis result"):
        benchmark(Path("demo.dem"), report.player_steam_id, runs=2)


def test_benchmark_surfaces_child_failure(monkeypatch, report):
    monkeypatch.setattr(
        "cs_map_trainer.benchmark.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b"", stderr=b"Not a CS2 demo"),
    )
    with pytest.raises(DemoError, match="run 1 failed.*Not a CS2 demo"):
        benchmark(Path("demo.dem"), report.player_steam_id)


def test_benchmark_surfaces_timeout(monkeypatch, report):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("analyze", 1)

    monkeypatch.setattr("cs_map_trainer.benchmark.subprocess.run", timeout)
    with pytest.raises(DemoError, match="run 1 exceeded 1 seconds"):
        benchmark(Path("demo.dem"), report.player_steam_id, timeout_seconds=1)


def test_benchmark_rejects_success_exit_with_invalid_stdout(monkeypatch, report):
    monkeypatch.setattr(
        "cs_map_trainer.benchmark.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"not json", stderr=b""),
    )
    with pytest.raises(DemoError, match="invalid analysis report"):
        benchmark(Path("demo.dem"), report.player_steam_id)


@pytest.mark.parametrize(
    "options",
    [
        {"runs": 0},
        {"timeout_seconds": 0},
        {"max_scenarios": 0},
        {"contact_window_ticks": 0},
    ],
)
def test_invalid_benchmark_parameters_are_explicit_errors(report, options):
    with pytest.raises(DemoError, match="positive"):
        benchmark(Path("demo.dem"), report.player_steam_id, **options)
