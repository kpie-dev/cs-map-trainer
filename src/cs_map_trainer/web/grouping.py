"""One presentation of practice groups for reports, navigation and the library."""

from cs_map_trainer.analysis import BASE_LIMITATIONS
from cs_map_trainer.callouts import format_place_name
from cs_map_trainer.training_groups import training_groups


def present_groups(report, selected_ids):
    rows = []
    for group in training_groups(report.scenario_document):
        members = []
        for scenario in group.members:
            locations = report.scenario_locations.get(scenario.scenario_id)
            members.append(
                {
                    "scenario": scenario,
                    "locations": locations,
                    "player_location": (
                        format_place_name(scenario.map.name, locations.player)
                        or "Location unavailable in demo"
                    )
                    if locations
                    else "Not recorded in this report",
                    "opponent_location": (
                        format_place_name(scenario.map.name, locations.opponent)
                        or "Location unavailable in demo"
                    )
                    if locations
                    else "Not recorded in this report",
                    "selected": scenario.scenario_id in selected_ids,
                }
            )
        selected = [member for member in members if member["selected"]]
        rows.append(
            {
                "group_id": group.group_id,
                "members": members,
                "selected": selected,
                "selected_count": len(selected),
                "all_selected": len(selected) == len(members),
                "partial": bool(selected) and len(selected) != len(members),
                "first": selected[0] if selected else members[0],
                "priority": group.priority_label,
                "warnings": [
                    code for code in group.members[0].limitations if code not in BASE_LIMITATIONS
                ],
            }
        )
    return rows
