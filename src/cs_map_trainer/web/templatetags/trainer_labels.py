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
def exclusion_label(code):
    return EXCLUSIONS.get(code, code)


@register.filter
def export_detail_label(code):
    return EXPORT_DETAILS.get(code, code)
