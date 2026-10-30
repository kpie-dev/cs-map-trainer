"""Experimental Yprac console sequence, not a verified game integration."""

from dataclasses import dataclass
from decimal import Decimal

from cs_map_trainer.maps import SUPPORTED_MAP_NAMES, SUPPORTED_MAPS
from cs_map_trainer.scenarios import Scenario
from cs_map_trainer.weapons import GUNS

EXPORTER_VERSION = "yprac-sandbox-prototype-v1"
WORKSHOP_ID = "3070715607"
COMPATIBILITY = "unverified_in_game"
BOT_PLAYER_INDEX = 2
BOT_ENTITY_INDEX = 2
BOT_TARGET = "cmt_v1_bot"
TELEPORT_TARGET = "cmt_v1_teleport"
MAX_COORDINATE = 16384
MAX_CONSOLE_BYTES = 1023
WEAPONS = {weapon: weapon for weapon in sorted(GUNS)}
ASSUMPTIONS = (
    "isolated_local_session_one_human",
    f"bot_player_index_{BOT_PLAYER_INDEX}_after_bot_kick_unverified",
    f"bot_pawn_entity_index_{BOT_ENTITY_INDEX}_unverified_separate_from_player_index",
    "bot_spawn_and_jointeam_ready_before_next_command_unverified",
    "point_teleport_sets_bot_eye_angles_unverified",
    "console_entity_io_and_yprac_chat_ordering_unverified",
    "yprac_weapon_identifiers_and_active_weapon_unverified",
    "target_map_geometry_and_client_access_unverified",
    "helper_entity_creation_and_cleanup_ordering_unverified",
)
SESSION_CHANGES = (
    "sv_cheats=1",
    "mp_limitteams=0",
    "mp_autoteambalance=0",
    "bot_quota_mode=normal",
    "bot_quota=0_before_adding_one_bot",
    "bot_stop=1",
    "all_existing_bots_kicked",
    "human_team_position_angles_and_weapon_changed",
    f"entity_index_{BOT_ENTITY_INDEX}_targetname_changed",
    f"{TELEPORT_TARGET}_created_and_removed",
)
ALLOWED_COMMANDS = frozenset(
    (
        "sv_cheats",
        "mp_limitteams",
        "mp_autoteambalance",
        "bot_quota_mode",
        "bot_quota",
        "bot_stop",
        "bot_kick",
        "jointeam",
        "bot_add_t",
        "bot_add_ct",
        "ent_setname",
        "setpos_player",
        "ent_remove",
        "ent_create",
        "ent_fire",
        "setpos_exact",
        "setang_exact",
        "say",
    )
)


class ExportError(ValueError):
    """A scenario or selection cannot be exported without changing its meaning."""


def _number(value: float) -> str:
    # Fixed-point round-trip formatting avoids exponents and arbitrary rounding.
    return "0" if value == 0 else format(Decimal(str(value)), "f")


@dataclass(frozen=True)
class ScenarioExport:
    scenario_id: str
    commands: tuple[str, ...]

    @property
    def console_line(self) -> str:
        return "; ".join(self.commands)

    @property
    def cfg(self) -> str:
        return f"// {EXPORTER_VERSION}: {COMPATIBILITY}\n" + "\n".join(self.commands) + "\n"


def export_scenario(scenario: Scenario) -> ScenarioExport:
    scenario = Scenario.model_validate(scenario.model_dump())
    if scenario.map.name not in SUPPORTED_MAPS:
        raise ExportError(f"Supported Yprac prototype maps: {SUPPORTED_MAP_NAMES}")
    for participant in (scenario.player, scenario.opponent):
        if participant.weapon not in WEAPONS:
            raise ExportError("Unsupported participant weapon")
        if any(abs(value) > MAX_COORDINATE for value in participant.position.model_dump().values()):
            raise ExportError("Position exceeds the prototype world-coordinate bounds")
        if participant.view_angles.roll != 0:
            raise ExportError("Nonzero roll is not supported by the training prototype")
    if "synthetic_not_playable" in scenario.limitations:
        raise ExportError("The synthetic non-playable fixture is not a training scenario")

    player, opponent = scenario.player, scenario.opponent
    bot_xyz = " ".join(_number(value) for value in opponent.position.model_dump().values())
    bot_angles = " ".join(_number(value) for value in opponent.view_angles.model_dump().values())
    player_xyz = " ".join(_number(value) for value in player.position.model_dump().values())
    player_angles = " ".join(_number(value) for value in player.view_angles.model_dump().values())
    commands = (
        "sv_cheats 1",
        "mp_limitteams 0",
        "mp_autoteambalance 0",
        "bot_quota_mode normal",
        "bot_quota 0",
        "bot_stop 1",
        "bot_kick",
        f"jointeam {2 if player.side == 'T' else 3}",
        f"bot_add_{opponent.side.lower()}",
        f"ent_setname {BOT_TARGET} {BOT_ENTITY_INDEX}",
        f"setpos_player {BOT_PLAYER_INDEX} {bot_xyz}",
        f"ent_remove {TELEPORT_TARGET}",
        f'ent_create point_teleport {{ targetname {TELEPORT_TARGET} origin "{bot_xyz}" '
        f'angles "{bot_angles}" teleport_use_current_angle 0 }}',
        f"ent_fire {TELEPORT_TARGET} TeleportEntityToCurrentPos {BOT_TARGET}",
        f"ent_fire {TELEPORT_TARGET} Kill",
        f"setpos_exact {player_xyz}",
        f"setang_exact {player_angles}",
        f'say "weapon {WEAPONS[player.weapon]}"',
        f'say "botweapon {WEAPONS[opponent.weapon]}"',
    )
    if any(command.split()[0] not in ALLOWED_COMMANDS for command in commands):
        raise ExportError("Exporter generated a command outside its allowlist")
    result = ScenarioExport(scenario.scenario_id, commands)
    if len(result.console_line.encode("ascii")) > MAX_CONSOLE_BYTES:
        raise ExportError("Console sequence exceeds the prototype single-paste byte budget")
    return result
