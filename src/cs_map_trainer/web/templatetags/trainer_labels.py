from django import template

from cs_map_trainer.web.presentation import EXCLUSIONS, EXPORT_DETAILS, LIMITATIONS

register = template.Library()


@register.filter
def win_rate_percent(value: float) -> str:
    return f"{value * 100:.1f}".removesuffix(".0") + "%"


@register.filter
def limitation_label(code):
    return LIMITATIONS.get(code, code)


@register.filter
def limitation_short(code):
    return {
        "opponent_aim_inferred_toward_player": "Opponent aim estimated (equal eye heights)",
        "player_blinded": "Player flashed",
        "opponent_blinded": "Opponent flashed",
        "player_flash_unknown": "Player flash unknown",
        "opponent_flash_unknown": "Opponent flash unknown",
        "player_posture_unknown": "Player posture unknown",
        "opponent_posture_unknown": "Opponent posture unknown",
        "penetration_unknown": "Shot penetration unknown",
        "through_smoke_unknown": "Shot through smoke unknown",
    }.get(code, LIMITATIONS.get(code, code))


@register.filter
def exclusion_label(code):
    return EXCLUSIONS.get(code, code)


@register.filter
def export_detail_label(code):
    return EXPORT_DETAILS.get(code, code)
