"""Selection and reproducible archives shared by the CLI and future web backend."""

import json
from dataclasses import dataclass
from io import BytesIO
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pydantic import JsonValue, TypeAdapter

from cs_map_trainer.exporting import (
    ASSUMPTIONS,
    BOT_ENTITY_INDEX,
    BOT_PLAYER_INDEX,
    COMPATIBILITY,
    EXPORTER_VERSION,
    SESSION_CHANGES,
    WORKSHOP_ID,
    ExportError,
    export_scenario,
)
from cs_map_trainer.maps import SUPPORTED_MAPS, Integration, map_label
from cs_map_trainer.scenarios import ContractModel, MapIdentity, ScenarioDocument, Source
from cs_map_trainer.training_groups import training_groups


class PackEntry(ContractModel):
    scenario_id: str
    map: MapIdentity
    source: Source
    limitations: list[str]
    console_file: str
    cfg_file: str | None


class PackManifest(ContractModel):
    pack_version: Literal[1] = 1
    scenario_schema_version: Literal[1] = 1
    exporter_version: str
    compatibility: Literal["unverified_in_game"]
    integration: Integration = "yprac_hub_mirage_sandbox"
    workshop_id: str
    assumed_bot_player_index: int
    assumed_bot_entity_index: int
    assumptions: list[str]
    session_changes: list[str]
    available_scenario_ids: list[str]
    selected_scenario_ids: list[str]
    omitted_scenario_ids: list[str]
    rejected_scenario_ids: list[str]
    entries: list[PackEntry]


@dataclass(frozen=True)
class TrainingPack:
    manifest: PackManifest
    archive: bytes


def load_scenarios(raw: bytes) -> ScenarioDocument:
    value = TypeAdapter(JsonValue).validate_json(raw)
    if isinstance(value, dict) and "analysis_version" in value:
        from cs_map_trainer.analysis import AnalysisReport

        report = AnalysisReport.model_validate_json(raw)
        if report.status != "candidates_ready" or report.scenario_document is None:
            raise ExportError("Analysis report contains no ready training candidates")
        document = report.scenario_document
        if any(
            scenario.map != report.map
            or scenario.source.demo_sha256 != report.demo_sha256
            or scenario.player.steam_id != report.player_steam_id
            or scenario.source.parser_version != report.parser_version
            or scenario.source.rules_version != report.rules_version
            for scenario in document.scenarios
        ):
            raise ExportError("Analysis report and scenario source metadata disagree")
        return document
    return ScenarioDocument.model_validate_json(raw)


def select_scenarios(
    document: ScenarioDocument,
    *,
    include: list[str] | None = None,
    reject: list[str] | None = None,
) -> ScenarioDocument:
    document = ScenarioDocument.model_validate(document.model_dump())
    rejected = [] if reject is None else reject
    available = {scenario.scenario_id for scenario in document.scenarios}
    for ids in (include, rejected):
        if ids is not None and (len(ids) != len(set(ids)) or not set(ids) <= available):
            raise ExportError("Selection contains duplicate or unknown scenario IDs")
    if include is not None and set(include) & set(rejected):
        raise ExportError("A scenario cannot be both included and rejected")
    selected = [
        scenario
        for scenario in document.scenarios
        if (include is None or scenario.scenario_id in include)
        and scenario.scenario_id not in rejected
    ]
    if not selected:
        raise ExportError("Selection contains no scenarios")
    return ScenarioDocument(schema_version=1, scenarios=selected)


def _instructions(manifest: PackManifest) -> str:
    targets = "\n".join(
        f"- {entry.console_file}"
        f"{f' / {entry.cfg_file}' if entry.cfg_file else ''}: "
        f"{map_label(entry.map.name)} ({entry.map.name}) / Sandbox."
        for entry in manifest.entries
    )
    return (
        "# Yprac training prototype — not verified in game\n\n"
        f"Exporter: {manifest.exporter_version}; compatibility: {manifest.compatibility}.\n"
        f"Target: Yprac Hub {manifest.workshop_id}, Sandbox.\n"
        f"Map for each file:\n{targets}\n\n"
        "These are prototype commands, not proof of a working import or available game mode.\n"
        "You need the Yprac client, access to the correct map and Sandbox, compatible geometry,\n"
        "and permission to use sv_cheats and entity commands. Check the client requirements\n"
        "and map before use. Do not use in matchmaking or on a shared server.\n"
        "Use an isolated local session with one human player and one bot only.\n\n"
        "Once you have opened the correct map in Sandbox, copy the ENTIRE line from one\n"
        "console/*.txt file and paste it once into the console. Use one scenario at a time.\n"
        "Before using a file for another map, switch to that map in Sandbox.\n"
        "To repeat a setup, paste the same line again. A chat restart is not assumed to\n"
        "preserve the setup. Optional cfg/*.cfg files run the same command sequence.\n"
        "To use a CFG, copy it to your own game/csgo/cfg/cmt_v1 directory without\n"
        "overwriting files, then run e.g. exec cmt_v1/scenario-0001.cfg.\n"
        "Do not combine multiple scenarios into one paste.\n\n"
        f"Bot player index {manifest.assumed_bot_player_index} and pawn entity index "
        f"{manifest.assumed_bot_entity_index} are TWO SEPARATE ASSUMPTIONS.\n"
        "Indices are not detected dynamically. ent_setname names entity "
        f"{manifest.assumed_bot_entity_index};\n"
        "point_teleport attempts to set its position and orientation. The bot's EYE direction,\n"
        "spawn readiness and command ordering have not been verified.\n"
        "Semicolons do not wait for spawning, chat handling or entity I/O operations.\n"
        "Successful command generation does not confirm a correct in-game setup.\n\n"
        "Commands kick all existing bots and change the player's team, position, aim angles\n"
        "and weapon, as well as global session settings. Previous values are not saved.\n"
        "Binds and autoexec.cfg are not changed. Leave the session when finished and check\n"
        "your settings before playing elsewhere. See the manifest for the full list of changes.\n\n"
        "scenarios.json and manifest.json contain source metadata and limitations, and may\n"
        "include player identifiers. Do not publish the pack as a diagnostic log.\n"
        "training-groups.json adds practice group identity and selected membership without\n"
        "replacing scenarios.json or the version-1 manifest. Run every selected member\n"
        "separately; the first member is a preview, not the entire group training.\n"
        "opponent_aim_inferred_toward_player marks estimated aim, not aim measured from\n"
        "the demo. Movement, health, armor and human opponent behavior are not reconstructed.\n\n"
        "Separate CS2/Yprac checks are required for indices, spawn readiness, XYZ positions,\n"
        "eye direction, both players' weapons and teams, map compatibility and repeatability.\n"
    )


def build_pack(
    document: ScenarioDocument,
    *,
    include: list[str] | None = None,
    reject: list[str] | None = None,
    include_cfg: bool = False,
) -> TrainingPack:
    document = ScenarioDocument.model_validate(document.model_dump())
    selected = select_scenarios(document, include=include, reject=reject)
    selected_ids = [scenario.scenario_id for scenario in selected.scenarios]
    entries = []
    files = {"scenarios.json": selected.model_dump_json(indent=2) + "\n"}
    for index, scenario in enumerate(selected.scenarios, start=1):
        exported = export_scenario(scenario)
        stem = f"scenario-{index:04d}"
        console_file = f"console/{stem}.txt"
        cfg_file = f"cfg/{stem}.cfg" if include_cfg else None
        files[console_file] = exported.console_line + "\n"
        if cfg_file is not None:
            files[cfg_file] = exported.cfg
        entries.append(
            PackEntry(
                scenario_id=scenario.scenario_id,
                map=scenario.map,
                source=scenario.source,
                limitations=scenario.limitations,
                console_file=console_file,
                cfg_file=cfg_file,
            )
        )
    manifest = PackManifest(
        exporter_version=EXPORTER_VERSION,
        compatibility=COMPATIBILITY,
        integration=(
            SUPPORTED_MAPS[selected.scenarios[0].map.name].integration
            if len({scenario.map.name for scenario in selected.scenarios}) == 1
            else "yprac_hub_multi_map_sandbox"
        ),
        workshop_id=WORKSHOP_ID,
        assumed_bot_player_index=BOT_PLAYER_INDEX,
        assumed_bot_entity_index=BOT_ENTITY_INDEX,
        assumptions=list(ASSUMPTIONS),
        session_changes=list(SESSION_CHANGES),
        available_scenario_ids=[scenario.scenario_id for scenario in document.scenarios],
        selected_scenario_ids=selected_ids,
        omitted_scenario_ids=[
            scenario.scenario_id
            for scenario in document.scenarios
            if scenario.scenario_id not in selected_ids
        ],
        rejected_scenario_ids=[
            scenario.scenario_id
            for scenario in document.scenarios
            if reject is not None and scenario.scenario_id in reject
        ],
        entries=entries,
    )
    files["manifest.json"] = manifest.model_dump_json(indent=2) + "\n"
    files["training-groups.json"] = (
        json.dumps(
            {
                "version": 1,
                "rule": "spatial-192-angle-30-weapon-class-v1",
                "groups": [
                    {
                        "group_id": group.group_id,
                        "available_scenario_ids": group.scenario_ids,
                        "selected_scenario_ids": [
                            sid for sid in group.scenario_ids if sid in selected_ids
                        ],
                        "weapon_priority": group.priority_label,
                    }
                    for group in training_groups(document)
                    if set(group.scenario_ids) & set(selected_ids)
                ],
            },
            indent=2,
        )
        + "\n"
    )
    files["README.txt"] = _instructions(manifest)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = ZipInfo(name)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))
    return TrainingPack(manifest, output.getvalue())
