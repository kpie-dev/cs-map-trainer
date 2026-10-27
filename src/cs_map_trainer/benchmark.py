"""Repeat the actual CLI pipeline in fresh processes, without clearing OS caches."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from cs_map_trainer.analysis import AnalysisReport, Metrics
from cs_map_trainer.parsing import DemoError
from cs_map_trainer.scenarios import ContractModel, MapIdentity, SteamID


class BenchmarkRun(ContractModel):
    run: int
    phase: Literal["first_observed", "repeat"]
    process_wall_seconds: float
    output_bytes: int
    metrics: Metrics


class BenchmarkReport(ContractModel):
    benchmark_version: Annotated[int, Field(ge=1, le=1)] = 1
    analysis_version: int
    parser_version: str
    rules_version: str
    demo_sha256: str
    player_steam_id: SteamID
    map: MapIdentity
    python_version: str
    platform: str
    status: Literal["candidates_ready", "no_eligible_duels"]
    eligible_candidates: int
    eligible_wins: int
    max_scenarios: int
    contact_window_ticks: int
    group_cell_units: float
    runs: list[BenchmarkRun]
    limitations: list[str]


def benchmark(
    path: Path,
    steam_id: str,
    *,
    runs: int = 3,
    timeout_seconds: int = 300,
    max_scenarios: int = 10,
    contact_window_ticks: int = 128,
) -> BenchmarkReport:
    if min(runs, timeout_seconds, max_scenarios, contact_window_ticks) < 1:
        raise DemoError("Benchmark parameters must be positive")
    command = [
        sys.executable,
        "-m",
        "cs_map_trainer.cli",
        "analyze",
        str(path),
        "--steam-id",
        steam_id,
        "--max-scenarios",
        str(max_scenarios),
        "--contact-window-ticks",
        str(contact_window_ticks),
    ]
    measured: list[BenchmarkRun] = []
    reference: AnalysisReport | None = None
    for index in range(1, runs + 1):
        started = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise DemoError(f"Benchmark run {index} exceeded {timeout_seconds} seconds") from error
        elapsed = time.perf_counter() - started
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace")[:2000].strip()
            raise DemoError(f"Benchmark run {index} failed (exit {result.returncode}): {detail}")
        try:
            report = AnalysisReport.model_validate_json(result.stdout)
        except ValidationError as error:
            raise DemoError(f"Benchmark run {index} produced an invalid analysis report") from error
        if reference is None:
            reference = report
        elif report.model_dump(exclude={"metrics"}) != reference.model_dump(exclude={"metrics"}):
            raise DemoError(f"Benchmark run {index} changed the analysis result between runs")
        measured.append(
            BenchmarkRun(
                run=index,
                phase="first_observed" if index == 1 else "repeat",
                process_wall_seconds=elapsed,
                output_bytes=len(result.stdout),
                metrics=report.metrics,
            )
        )

    assert reference is not None
    return BenchmarkReport(
        analysis_version=reference.analysis_version,
        parser_version=reference.parser_version,
        rules_version=reference.rules_version,
        demo_sha256=reference.demo_sha256,
        player_steam_id=reference.player_steam_id,
        map=reference.map,
        python_version=sys.version.split()[0],
        platform=sys.platform,
        status=reference.status,
        eligible_candidates=reference.eligible_candidates,
        eligible_wins=reference.eligible_wins,
        max_scenarios=max_scenarios,
        contact_window_ticks=reference.contact_window_ticks,
        group_cell_units=reference.group_cell_units,
        runs=measured,
        limitations=[
            "os_file_cache_not_cleared",
            "first_observed_is_not_guaranteed_cold",
            "child_cpu_excludes_interpreter_and_import_startup",
            "process_wall_includes_startup_and_json_output",
            "io_bytes_not_measured",
            "hardware_and_container_limits_not_inferred",
        ],
    )
