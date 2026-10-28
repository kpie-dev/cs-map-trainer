import json
import os
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from cs_map_trainer.artifacts import write_new_file
from cs_map_trainer.exporting import ASSUMPTIONS, ExportError, export_scenario
from cs_map_trainer.packs import build_pack, load_scenarios, select_scenarios
from cs_map_trainer.scenarios import ScenarioDocument


@pytest.fixture
def document(training_document):
    scenario = training_document.scenarios[0]
    return ScenarioDocument(
        schema_version=1,
        scenarios=[
            scenario.model_copy(update={"scenario_id": f"duel-{i}"}, deep=True) for i in range(1, 4)
        ],
    )


def test_selection_preserves_source_order_and_input(document):
    result = select_scenarios(document, include=["duel-3", "duel-1"])
    assert [scenario.scenario_id for scenario in result.scenarios] == ["duel-1", "duel-3"]
    assert len(document.scenarios) == 3
    assert [
        scenario.scenario_id for scenario in select_scenarios(document, reject=["duel-2"]).scenarios
    ] == ["duel-1", "duel-3"]


@pytest.mark.parametrize(
    "options",
    [
        {"include": ["unknown"]},
        {"include": ["duel-1", "duel-1"]},
        {"reject": ["unknown"]},
        {"reject": ["duel-1", "duel-1"]},
        {"include": ["duel-1"], "reject": ["duel-1"]},
        {"include": []},
        {"reject": ["duel-1", "duel-2", "duel-3"]},
    ],
)
def test_invalid_selections_fail_explicitly(document, options):
    with pytest.raises(ExportError):
        build_pack(document, **options)


@pytest.mark.parametrize("include_cfg", [False, True])
def test_archive_manifest_and_commands(document, include_cfg):
    pack = build_pack(document, reject=["duel-2"], include_cfg=include_cfg)
    assert pack.archive == build_pack(document, reject=["duel-2"], include_cfg=include_cfg).archive
    manifest = pack.manifest
    assert manifest.compatibility == "unverified_in_game"
    assert manifest.workshop_id == "3070715607"
    assert manifest.assumed_bot_player_index == manifest.assumed_bot_entity_index == 2
    assert manifest.assumptions == list(ASSUMPTIONS)
    assert manifest.selected_scenario_ids == ["duel-1", "duel-3"]
    assert manifest.rejected_scenario_ids == ["duel-2"]
    assert manifest.omitted_scenario_ids == ["duel-2"]
    assert manifest.available_scenario_ids == ["duel-1", "duel-2", "duel-3"]
    with ZipFile(BytesIO(pack.archive)) as archive:
        expected = {
            "manifest.json",
            "scenarios.json",
            "README.txt",
            "console/scenario-0001.txt",
            "console/scenario-0002.txt",
        }
        if include_cfg:
            expected |= {"cfg/scenario-0001.cfg", "cfg/scenario-0002.cfg"}
        assert set(archive.namelist()) == expected
        assert archive.testzip() is None
        assert json.loads(archive.read("manifest.json")) == manifest.model_dump(mode="json")
        selected = ScenarioDocument.model_validate_json(archive.read("scenarios.json"))
        for scenario, entry in zip(selected.scenarios, manifest.entries, strict=True):
            exported = export_scenario(scenario)
            assert archive.read(entry.console_file).decode() == exported.console_line + "\n"
            assert entry.source == scenario.source
            assert entry.map == scenario.map
            assert entry.limitations == scenario.limitations
            if entry.cfg_file:
                assert archive.read(entry.cfg_file).decode() == exported.cfg
        instructions = archive.read("README.txt").decode()
        assert "niezweryfikowane" in instructions
        assert "DWA ODRĘBNE ZAŁOŻENIA" in instructions
        assert "Średniki nie czekają" in instructions


def test_manifest_distinguishes_omitted_from_rejected(document):
    manifest = build_pack(document, include=["duel-1"], reject=["duel-3"]).manifest
    assert manifest.omitted_scenario_ids == ["duel-2", "duel-3"]
    assert manifest.rejected_scenario_ids == ["duel-3"]


def test_bad_unselected_scenario_does_not_block_selected_pack(document):
    document.scenarios[1].player.weapon = "knife"
    with pytest.raises(ExportError, match="weapon"):
        build_pack(document)
    assert build_pack(document, reject=["duel-2"]).manifest.selected_scenario_ids == [
        "duel-1",
        "duel-3",
    ]


@pytest.mark.parametrize("scenario_id", ["../outside", "duel\nquit", "duel;quit"])
def test_unsafe_ids_cannot_be_archive_paths(document, scenario_id):
    document.scenarios[0].scenario_id = scenario_id
    with pytest.raises(ValidationError):
        build_pack(document)


def test_scenario_document_loads(training_document):
    assert load_scenarios(training_document.model_dump_json().encode()) == training_document


def test_analysis_report_loads_without_reanalysis(training_report, training_document):
    assert load_scenarios(training_report.model_dump_json().encode()) == training_document


@pytest.mark.parametrize("status", ["candidates_ready", "no_eligible_duels"])
def test_report_without_document_fails(training_report, status):
    training_report.status = status
    training_report.scenario_document = None
    with pytest.raises(ExportError, match="no ready"):
        load_scenarios(training_report.model_dump_json().encode())


def test_report_with_nonready_status_fails(training_report):
    training_report.status = "no_eligible_duels"
    with pytest.raises(ExportError, match="no ready"):
        load_scenarios(training_report.model_dump_json().encode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("demo_sha256", "1" * 64),
        ("player_steam_id", "76561198000000003"),
        ("parser_version", "other"),
        ("rules_version", "other"),
    ],
)
def test_report_metadata_mismatch_fails(training_report, field, value):
    setattr(training_report, field, value)
    with pytest.raises(ExportError, match="metadata disagree"):
        load_scenarios(training_report.model_dump_json().encode())


def test_report_map_mismatch_fails(training_report):
    training_report.map = training_report.map.model_copy(update={"game_build": 2})
    with pytest.raises(ExportError, match="metadata disagree"):
        load_scenarios(training_report.model_dump_json().encode())


@pytest.mark.parametrize("raw", [b"{}", b"[]", b"null", b"not-json", b"\xff"])
def test_invalid_input_fails_without_fallback(raw):
    with pytest.raises(ValidationError):
        load_scenarios(raw)


def test_unsupported_report_version_does_not_fall_back(training_report):
    raw = training_report.model_dump()
    raw["analysis_version"] = 1
    with pytest.raises(ValidationError):
        load_scenarios(json.dumps(raw).encode())


def test_atomic_artifact_write_preserves_existing_files(tmp_path):
    path = tmp_path / "pack.zip"
    write_new_file(path, b"complete")
    with pytest.raises(FileExistsError):
        write_new_file(path, b"replacement")
    assert path.read_bytes() == b"complete"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pack.zip"]


def test_artifact_does_not_follow_symlink(tmp_path):
    original = tmp_path / "original"
    original.write_bytes(b"private")
    output = tmp_path / "output"
    output.symlink_to(original)
    with pytest.raises(FileExistsError):
        write_new_file(output, b"replacement")
    assert original.read_bytes() == b"private"


@pytest.mark.parametrize("operation", ["link", "fsync"])
def test_artifact_failures_leave_no_partial_output(tmp_path, monkeypatch, operation):
    def fail(*args):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(os, operation, fail)
    with pytest.raises(OSError, match="synthetic"):
        write_new_file(tmp_path / "output.zip", b"complete")
    assert list(tmp_path.iterdir()) == []
