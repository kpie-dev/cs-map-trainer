from django.template import Context, Template

from cs_map_trainer.analysis import BASE_LIMITATIONS
from cs_map_trainer.exporting import ASSUMPTIONS, SESSION_CHANGES
from cs_map_trainer.web.presentation import EXPORT_DETAILS, LIMITATIONS, error_message


def test_core_limitations_and_export_details_have_readable_labels():
    assert set(BASE_LIMITATIONS) <= LIMITATIONS.keys()
    assert set(ASSUMPTIONS + SESSION_CHANGES) == EXPORT_DETAILS.keys()
    for label in [*LIMITATIONS.values(), *EXPORT_DETAILS.values()]:
        assert label.endswith(".")
        assert " " in label


def test_unknown_diagnostic_codes_remain_visible_and_escaped():
    template = Template(
        "{% load trainer_labels %}"
        "{{ code|limitation_label }} / {{ code|exclusion_label }} / {{ code|export_detail_label }}"
    )
    assert template.render(Context({"code": "<unknown>"})) == (
        "&lt;unknown&gt; / &lt;unknown&gt; / &lt;unknown&gt;"
    )
    assert error_message("new_error") == "The action failed. Error code: new_error"
