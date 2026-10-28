"""Selection and reproducible archives shared by the CLI and future web backend."""

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
from cs_map_trainer.scenarios import ContractModel, MapIdentity, ScenarioDocument, Source


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
    integration: Literal["yprac_hub_mirage_sandbox"] = "yprac_hub_mirage_sandbox"
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
    return (
        "# Yprac training prototype — niezweryfikowane w grze\n\n"
        f"Exporter: {manifest.exporter_version}; compatibility: {manifest.compatibility}.\n"
        f"Target: Yprac Hub {manifest.workshop_id}, Mirage / Sandbox.\n\n"
        "To prototyp komend, nie dowód działającego importu ani dostępności trybu.\n"
        "Wymagany klient Yprac, dostęp do właściwego Mirage/Sandbox, zgodna geometria\n"
        "i uprawnienia do sv_cheats/komend encji. Zweryfikuj wymagania klienta\n"
        "i mapę przed użyciem. Nie używaj na matchmakingu ani współdzielonym serwerze.\n"
        "Sesja musi być lokalna i odizolowana: tylko człowiek i jeden bot.\n\n"
        "Po wejściu do mapy i Sandbox skopiuj CAŁĄ pojedynczą linię z jednego\n"
        "pliku console/*.txt i wklej ją raz do konsoli. Jeden scenariusz naraz.\n"
        "Powtórka: ponownie wklej tę samą linię; nie zakładamy, że chatowy restart\n"
        "zachowuje ustawienie. Opcjonalne cfg/*.cfg wykonują tę samą sekwencję.\n"
        "Opcjonalnie skopiuj CFG do własnego katalogu game/csgo/cfg/cmt_v1,\n"
        "bez nadpisywania plików, i uruchom np. exec cmt_v1/scenario-0001.cfg.\n"
        "Nie łącz plików wielu scenariuszy w jedno wklejenie.\n\n"
        f"Indeks gracza bota {manifest.assumed_bot_player_index} i indeks jego encji/pawn "
        f"{manifest.assumed_bot_entity_index} to DWA ODRĘBNE ZAŁOŻENIA.\n"
        "Nie ma dynamicznego wyszukiwania indeksu. ent_setname nadaje nazwę encji "
        f"{manifest.assumed_bot_entity_index};\n"
        "point_teleport próbuje ustawić jej pozycję i orientację. Nie potwierdzono\n"
        "kierunku OCZU bota, gotowości po dodaniu ani kolejności wykonania.\n"
        "Średniki nie czekają na spawn, obsługę chatu ani operacje entity I/O.\n"
        "Brak błędu generowania nie oznacza poprawnego ustawienia w grze.\n\n"
        "Komendy wyrzucają wszystkie boty, zmieniają drużynę, pozycję, kąty i broń\n"
        "gracza oraz globalne ustawienia sesji. Nie zapisują poprzednich wartości.\n"
        "Nie zmieniają bindów ani autoexec.cfg. Po zakończeniu opuść tę sesję;\n"
        "przed dalszą grą sprawdź ustawienia. Pełna lista zmian jest w manifeście.\n\n"
        "scenarios.json i manifest.json zawierają źródła i ograniczenia; mogą\n"
        "zawierać identyfikatory graczy. Nie publikuj paczki jako logu.\n"
        "opponent_aim_inferred_toward_player oznacza przybliżony kierunek, nie\n"
        "pomiar z dema. Nie odtwarzamy ruchu, zdrowia, pancerza ani zachowania bota.\n\n"
        "Odbiór wymaga osobnych prób CS2/Yprac: indeksy, gotowość, XYZ, oczy,\n"
        "broń i strony obu uczestników, zgodność mapy i powtarzalność.\n"
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
    files["README.txt"] = _instructions(manifest)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = ZipInfo(name)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))
    return TrainingPack(manifest, output.getvalue())
