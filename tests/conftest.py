import json
from pathlib import Path

import pytest

from cs_map_trainer.maps import SUPPORTED_MAPS
from cs_map_trainer.scenarios import ScenarioDocument

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-scenarios.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(params=SUPPORTED_MAPS)
def training_document(payload, request):
    scenario = payload["scenarios"][0]
    scenario["map"]["name"] = request.param
    scenario["map"]["revision"] = "synthetic-export-test-not-runtime-evidence"
    scenario["limitations"] = [
        "synthetic_export_reference",
        "map_geometry_unverified",
        "opponent_aim_inferred_toward_player",
    ]
    return ScenarioDocument.model_validate(payload)


@pytest.fixture
def training_report(training_document):
    from cs_map_trainer.analysis import AnalysisReport, Metrics

    reference = training_document.scenarios[0]
    return AnalysisReport(
        status="candidates_ready",
        parser_version=reference.source.parser_version,
        rules_version=reference.source.rules_version,
        player_steam_id=reference.player.steam_id,
        demo_sha256=reference.source.demo_sha256,
        map=reference.map,
        contact_window_ticks=128,
        group_cell_units=256.0,
        deaths_considered=1,
        kills_considered=0,
        eligible_candidates=1,
        eligible_wins=0,
        omitted_by_limit=0,
        excluded=[],
        excluded_wins=[],
        groups=[],
        scenario_document=training_document,
        limitations=["synthetic_export_reference"],
        metrics=Metrics(
            wall_seconds=0.0,
            cpu_seconds=0.0,
            process_peak_rss_bytes=None,
            rss_scope="unavailable_on_platform",
            input_bytes=0,
        ),
    )
