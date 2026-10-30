"""CLI commands are exposed only when their implementation is available."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from cs_map_trainer.maps import SUPPORTED_MAP_NAMES
from cs_map_trainer.scenarios import ScenarioDocument, SteamID


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected a positive integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def _steam_id(value: str) -> str:
    try:
        return TypeAdapter(SteamID).validate_python(value)
    except ValidationError as error:
        raise argparse.ArgumentTypeError("Expected a 17-digit SteamID64") from error


def _demo_command(args: argparse.Namespace) -> int:
    from awpy import InvalidDemoError

    from cs_map_trainer.analysis import analyze, exclusion_counts, roster
    from cs_map_trainer.benchmark import benchmark
    from cs_map_trainer.parsing import DemoError, DemoReader

    try:
        if args.output is not None and args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        if args.command == "benchmark":
            result = benchmark(
                args.path,
                args.steam_id,
                runs=args.runs,
                timeout_seconds=args.timeout_seconds,
                max_scenarios=args.max_scenarios,
                contact_window_ticks=args.contact_window_ticks,
            )
        elif args.command == "players":
            result = roster(DemoReader(args.path))
        else:
            result = analyze(
                lambda: DemoReader(args.path),
                args.steam_id,
                max_scenarios=args.max_scenarios,
                contact_window_ticks=args.contact_window_ticks,
            )
            print(
                f"Candidates: {result.eligible_candidates}; selected: "
                f"{len(result.scenario_document.scenarios) if result.scenario_document else 0}; "
                f"comparable wins: {result.eligible_wins}; "
                f"excluded: {json.dumps(exclusion_counts(result), sort_keys=True)}",
                file=sys.stderr,
            )
        output = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(output, end="")
        else:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(output)
    except (OSError, DemoError, InvalidDemoError) as error:
        print(f"Demo processing failed: {error}", file=sys.stderr)
        return 1
    except ValidationError as error:
        print("Unsupported or incomplete parser data:", file=sys.stderr)
        for issue in error.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in issue["loc"]) or "document"
            print(f"  {location}: {issue['msg']}", file=sys.stderr)
        return 1
    return 0


def _training_command(args: argparse.Namespace) -> int:
    from cs_map_trainer.artifacts import write_new_file
    from cs_map_trainer.exporting import (
        BOT_ENTITY_INDEX,
        BOT_PLAYER_INDEX,
        COMPATIBILITY,
        ExportError,
        export_scenario,
    )
    from cs_map_trainer.packs import build_pack, load_scenarios, select_scenarios

    try:
        document = load_scenarios(args.path.read_bytes())
        if args.command == "export-scenario":
            selected = select_scenarios(document, include=[args.scenario_id])
            exported = export_scenario(selected.scenarios[0])
            output = (exported.cfg if args.cfg else exported.console_line + "\n").encode("utf-8")
        else:
            output = build_pack(
                document,
                include=args.include,
                reject=args.reject,
                include_cfg=args.include_cfg,
            ).archive
        if args.output is None:
            sys.stdout.write(output.decode("utf-8"))
        else:
            write_new_file(args.output, output)
    except (OSError, ExportError) as error:
        print(f"Training export failed: {error}", file=sys.stderr)
        return 1
    except ValidationError as error:
        print("Invalid training input:", file=sys.stderr)
        for issue in error.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in issue["loc"]) or "document"
            print(f"  {location}: {issue['msg']}", file=sys.stderr)
        return 1
    print(
        f"Experimental export: {COMPATIBILITY}. Assumed bot player index {BOT_PLAYER_INDEX} "
        f"AND pawn entity index {BOT_ENTITY_INDEX}; eyes, spawn, ordering, weapons "
        "and map geometry are unverified. "
        "Isolated local Yprac session on the scenario's map in Sandbox only; "
        "existing bots and session settings "
        "will be changed. See the pack manifest and instructions.",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cs-map-trainer",
        description="Analyze CS2 demos and validate scenarios; console export is not yet verified.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-scenarios", help="Validate a scenario JSON document")
    validate.add_argument("path", type=Path)
    commands.add_parser("schema", help="Print JSON Schema for the supported scenario version")
    players = commands.add_parser(
        "players", help=f"Read the roster of a CS2 .dem ({SUPPORTED_MAP_NAMES})"
    )
    players.add_argument("path", type=Path)
    players.add_argument("--output", type=Path, help="Write JSON to a new file instead of stdout")
    for name, help_text in (
        ("analyze", "Analyze comparable wins and losses; select lost-duel candidates"),
        ("benchmark", "Measure repeated analyses in fresh processes"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("path", type=Path)
        command.add_argument("--steam-id", type=_steam_id, required=True)
        command.add_argument("--max-scenarios", type=_positive_int, default=10)
        command.add_argument("--contact-window-ticks", type=_positive_int, default=128)
        command.add_argument(
            "--output", type=Path, help="Write JSON to a new file instead of stdout"
        )
        if name == "benchmark":
            command.add_argument("--runs", type=_positive_int, default=3)
            command.add_argument("--timeout-seconds", type=_positive_int, default=300)
    export = commands.add_parser(
        "export-scenario", help="Export one experimental, unverified Yprac console sequence"
    )
    export.add_argument("path", type=Path, help="Scenario document v1 or analysis report v2")
    export.add_argument("--scenario-id", required=True)
    export.add_argument("--cfg", action="store_true", help="Emit optional CFG instead of one line")
    export.add_argument("--output", type=Path, help="Write to a new file instead of stdout")
    pack = commands.add_parser(
        "build-pack", help="Build an experimental Yprac ZIP with manifest and instructions"
    )
    pack.add_argument("path", type=Path, help="Scenario document v1 or analysis report v2")
    pack.add_argument("--include", action="append", help="Include an ID; repeat for more IDs")
    pack.add_argument("--reject", action="append", help="Reject an ID; repeat for more IDs")
    pack.add_argument(
        "--include-cfg", action="store_true", help="Include optional per-scenario CFG"
    )
    pack.add_argument("--output", type=Path, required=True, help="Write ZIP to a new file")
    args = parser.parse_args(argv)

    if args.command in ("players", "analyze", "benchmark"):
        return _demo_command(args)

    if args.command in ("export-scenario", "build-pack"):
        return _training_command(args)

    if args.command == "schema":
        print(json.dumps(ScenarioDocument.model_json_schema(), indent=2))
        return 0

    try:
        raw = args.path.read_bytes()
    except OSError as error:
        print(f"Cannot read scenario document: {error}", file=sys.stderr)
        return 1

    try:
        document = ScenarioDocument.model_validate_json(raw)
    except ValidationError as error:
        print("Invalid scenario document:", file=sys.stderr)
        for issue in error.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in issue["loc"]) or "document"
            print(f"  {location}: {issue['msg']}", file=sys.stderr)
        return 1

    print(
        f"Valid schema v{document.schema_version}: {len(document.scenarios)} scenario(s). "
        "Game compatibility and import have not been verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
