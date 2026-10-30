"""Private roster editing and immutable per-upload player snapshots."""

from django.db import transaction

from .entitlements import coach_access
from .identity import lock_account
from .models import Team, TeamMember
from .services import IntakeError, validate_player_steam_id


def roster_members(user):
    return TeamMember.objects.filter(team__owner=user).order_by("position", "pk")


@transaction.atomic
def save_roster(user, players):
    user = lock_account(user)
    if not user.is_active:
        raise IntakeError("account_blocked", 403)
    if not coach_access(user):
        raise IntakeError("coach_required", 403)
    if not isinstance(players, list) or not 1 <= len(players) <= 5:
        raise IntakeError("invalid_team_roster", 400)
    cleaned = []
    seen = set()
    for player in players:
        if not isinstance(player, dict) or set(player) - {"steam_id", "name"}:
            raise IntakeError("invalid_team_roster", 400)
        steam_id = validate_player_steam_id(player.get("steam_id"))
        name = player.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 64 or steam_id in seen:
            raise IntakeError("invalid_team_roster", 400)
        cleaned.append((steam_id, name.strip()))
        seen.add(steam_id)
    team, _ = Team.objects.get_or_create(owner=user)
    team.members.all().delete()
    TeamMember.objects.bulk_create(
        TeamMember(team=team, steam_id=steam_id, name=name, position=position)
        for position, (steam_id, name) in enumerate(cleaned)
    )
    return list(roster_members(user))
