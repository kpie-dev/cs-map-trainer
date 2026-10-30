"""Resource-limited child process; no database or R2 credentials are required."""

import json
import os
import resource
import signal
import sys
from pathlib import Path

from cs_map_trainer.web.processes import terminate_with_parent


def main():
    terminate_with_parent(int(os.environ["PARSER_PARENT_PID"]))
    path, steam_id, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    memory = int(os.environ["PARSER_MEMORY_BYTES"])
    seconds = int(os.environ["PARSER_TIMEOUT_SECONDS"])
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(seconds)
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    from pydantic import ValidationError

    from cs_map_trainer.analysis import analyze, roster
    from cs_map_trainer.parsing import DemoError, DemoReader
    from cs_map_trainer.team_analysis import TeamAnalysisRequest, analyze_team

    try:
        team_ids = None
        if steam_id.lstrip().startswith("["):
            team_ids = TeamAnalysisRequest(steam_ids=json.loads(steam_id)).steam_ids
        reader = DemoReader(path)
        if team_ids is not None:
            result = analyze_team(reader, team_ids).model_dump(mode="json")
        elif steam_id not in {player.steam_id for player in roster(reader).players}:
            result = {"error": "linked_player_not_in_demo"}
        else:
            report = analyze(lambda: reader, steam_id)
            result = {
                "report": report.model_dump(mode="json"),
                "error": None,
            }
    except (DemoError, ValidationError, json.JSONDecodeError):
        result = {"error": "unsupported_or_invalid_demo"}
    with output.open("x") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    main()
