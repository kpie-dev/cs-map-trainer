import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from html import unescape
from threading import Event
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import override

from cs_map_trainer.analysis import BASE_LIMITATIONS
from cs_map_trainer.exporting import export_scenario
from cs_map_trainer.maps import SUPPORTED_MAP_LABELS, SUPPORTED_MAP_NAMES, map_label
from cs_map_trainer.web import practice, services
from cs_map_trainer.web.models import PracticeReview, Upload
from cs_map_trainer.web.presentation import LIMITATIONS, error_message
from cs_map_trainer.web.templatetags.trainer_labels import limitation_short

pytestmark = pytest.mark.django_db


def test_supported_maps_are_shared_by_upload_history_and_error(api):
    for path in ("/", reverse("history")):
        response = api.get(path)
        assert response.status_code == 200
        text = response.content.decode()
        assert SUPPORTED_MAP_LABELS in text
        assert "Mirage or Dust2" not in text
    assert SUPPORTED_MAP_NAMES in api.get("/").content.decode()
    assert SUPPORTED_MAP_LABELS in error_message("unsupported_or_invalid_demo")


@pytest.fixture
def completed_upload(upload, training_report):
    report = training_report.model_dump(mode="json")
    second = deepcopy(report["scenario_document"]["scenarios"][0])
    second["scenario_id"] = "second-scenario"
    report["scenario_document"]["scenarios"].append(second)
    Upload.objects.filter(pk=upload.pk).update(
        state=Upload.State.READY,
        report=report,
        cleanup_pending=False,
        input_deleted_at=timezone.now(),
    )
    upload.refresh_from_db()
    return upload


def scenario_id(upload):
    return upload.report["scenario_document"]["scenarios"][0]["scenario_id"]


def review_url(upload):
    return reverse("review", args=[upload.pk, scenario_id(upload)])


def rate(upload, rating):
    practice.review_scenario(upload.owner, upload.pk, scenario_id(upload), rating)
    return upload.practice_reviews.first()


@pytest.mark.parametrize(
    "path", ["/", "/accounts/login/", "/accounts/signup/", "/accounts/password/reset/"]
)
def test_public_pages_use_shared_hud(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert b"trainer/app.css" in response.content
    assert b"trainer/app.js" in response.content
    assert b"CS2 DEMO REWIND" in response.content
    assert b"cdn.tailwindcss.com" not in response.content


@pytest.mark.parametrize(
    "path, heading",
    [
        ("/", "You lost"),
        ("/accounts/login/", "Sign In"),
        ("/accounts/signup/", "Sign Up"),
        ("/accounts/password/reset/", "Password Reset"),
    ],
)
def test_public_pages_stay_english_for_polish_browser(client, path, heading):
    response = client.get(path, HTTP_ACCEPT_LANGUAGE="pl-PL,pl;q=0.9")
    assert response.status_code == 200
    assert b'<html lang="en">' in response.content
    assert heading in response.content.decode()
    assert b"Skip to content" in response.content
    assert django_settings.LANGUAGE_CODE == "en"
    assert django_settings.LANGUAGES == [("en", "English")]
    assert django_settings.USE_I18N is False


def test_auth_validation_and_reset_email_are_english(client, user):
    response = client.post(
        "/accounts/login/",
        {"login": "not-an-email", "password": "wrong"},
        HTTP_ACCEPT_LANGUAGE="pl",
    )
    assert response.status_code == 200
    assert b"Enter a valid email address." in response.content
    response = client.post(
        "/accounts/password/reset/",
        {"email": user.email},
        HTTP_ACCEPT_LANGUAGE="pl",
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert "Password Reset" in mail.outbox[0].subject
    assert "Click the link below to reset your password." in mail.outbox[0].body
    assert "/accounts/password/reset/key/" in mail.outbox[0].body


def test_signup_and_confirmation_email_are_english(client):
    response = client.post(
        "/accounts/signup/",
        {
            "email": "new-player@example.test",
            "password1": "a-unique-player-password-9843",
            "password2": "a-unique-player-password-9843",
        },
        HTTP_ACCEPT_LANGUAGE="pl",
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert "Please Confirm Your Email Address" in mail.outbox[0].subject
    assert "To confirm this is correct, go to" in mail.outbox[0].body
    assert "/accounts/confirm-email/" in mail.outbox[0].body
    response = client.get(response.url, HTTP_ACCEPT_LANGUAGE="pl")
    assert b"Verify Your Email Address" in response.content


def test_english_copy_ignores_explicit_translation_override(api, completed_upload):
    rate(completed_upload, "hard")
    current = completed_upload.report["scenario_document"]["scenarios"][0]
    with override("pl"):
        response = api.get(reverse("training", args=[completed_upload.pk]))
    text = response.content.decode()
    assert '<html lang="en">' in text
    assert "Copy CS2 commands" in text
    assert "Rate your practice" not in text
    assert "Rated:" not in text
    assert f"XYZ {current['player']['position']['x']:.2f} /" in text
    assert "PLAYER /" in text
    assert "Bot player index 2 after removing existing bots is assumed, not verified." in text


def test_account_uses_english_price_and_unambiguous_dates(api, user):
    from cs_map_trainer.web.models import BillingAccount

    synced = timezone.now().replace(month=10, day=29)
    BillingAccount.objects.create(owner=user, synced_at=synced)
    response = api.get("/account/", HTTP_ACCEPT_LANGUAGE="pl")
    text = response.content.decode()
    assert "Pro / $7.99/month" in text
    assert f"Status last confirmed: {date_format(synced, 'j M Y, H:i')} UTC." in text


@pytest.mark.parametrize(
    "rating,label",
    [("done", "Done"), ("easy", "Easy"), ("hard", "Hard"), ("irrelevant", "Not useful")],
)
def test_saved_ratings_use_english_labels(api, completed_upload, rating, label):
    review = rate(completed_upload, rating)
    assert review.get_rating_display() == label
    response = api.get(reverse("training", args=[completed_upload.pk]))
    assert f'<p class="badge">{label}</p>' not in response.content.decode()
    assert completed_upload.practice_reviews.get().pk == review.pk
    library = api.get("/practice/")
    assert library.context["page"].paginator.count == 1
    assert library.context["page"][0]["group"]["selected_count"] == 2
    assert "Next review:" not in library.content.decode()


def test_known_limitations_and_exclusions_have_readable_labels(api, completed_upload):
    report = completed_upload.report
    report["limitations"] = ["small_samples_do_not_establish_skill"]
    report["excluded"] = [{"death_tick": 123, "reason": "multi_party_damage"}]
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    text = api.get(reverse("report", args=[completed_upload.pk])).content.decode()
    assert "Small samples do not establish player skill." in text
    assert "Damage exchange involved additional players" in text
    assert "Excluded losses" in text
    assert "Missing opponent aim angles are estimated toward the player" in text


@pytest.mark.parametrize("path", ["/history/", "/practice/", "/account/"])
def test_anonymous_private_pages_redirect_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert "no-store" in response["Cache-Control"]


def test_onboarding_does_not_expose_upload_before_verification(api, user):
    EmailAddress.objects.filter(user=user).update(verified=False)
    assert b'id="upload-form"' not in api.get("/").content
    assert api.get("/history/").url == "/accounts/email/"
    assert api.get("/practice/").url == "/accounts/email/"
    assert api.get("/account/").status_code == 200
    EmailAddress.objects.filter(user=user).update(verified=True)
    response = api.get("/")
    assert b'id="upload-form"' in response.content
    assert "No Steam sign-in required" in response.content.decode()
    assert b"OpenID" not in api.get("/account/").content


def test_home_has_rights_csrf_and_actual_quota(api, upload):
    response = api.get("/")
    assert b'id="upload-form"' in response.content
    assert b'id="upload-rights"' in response.content
    assert b"csrfmiddlewaretoken" in response.content
    assert b"1/3" in response.content
    assert b"CS2 ONLY" in response.content
    assert SUPPORTED_MAP_NAMES in response.content.decode()
    assert b"UNCOMPRESSED .DEM / UP TO 1 GiB" in response.content
    assert "no-store" in response["Cache-Control"]
    response = api.get(f"/uploads/{upload.pk}/")
    assert (
        f"Analyzed SteamID: <strong>{upload.player_steam_id}</strong>" in response.content.decode()
    )


def test_account_and_login_redirect(api, user, client):
    response = api.get("/account/")
    assert b"No Steam sign-in or account linking required." in response.content
    assert b"player@example.test" in response.content
    client.logout()
    result = client.post("/accounts/login/", {"login": user.email, "password": "some-password"})
    assert result.status_code == 302
    assert result.url == "/history/"


@pytest.mark.parametrize(
    "path", ["/accounts/email/", "/accounts/password/change/", "/accounts/logout/"]
)
def test_styled_allauth_pages_with_private_header_are_not_cached(api, path):
    response = api.get(path)
    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    assert b"trainer/app.css" in response.content


@pytest.mark.parametrize(
    "state", ["uploading", "queued", "running", "unsupported", "failed", "expired"]
)
def test_report_statuses_are_explicit(api, upload, state):
    Upload.objects.filter(pk=upload.pk).update(state=state, error_code="worker_lost")
    response = api.get(reverse("report", args=[upload.pk]))
    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    assert (b'id="job-status"' in response.content) == (state in services.ACTIVE)
    if state not in services.ACTIVE:
        assert "Analysis was interrupted" in response.content.decode()


def test_report_and_training_use_real_data_and_exporter(api, completed_upload):
    upload = completed_upload
    response = api.get(reverse("report", args=[upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    assert "practice priorities, not proof of mistakes" in text
    assert "opponent_aim_inferred_toward_player" in text
    assert scenario_id(upload) in text
    assert "NOT VERIFIED IN GAME" in text
    assert "NeoS1mple" not in text
    map_name = upload.report["map"]["name"]
    assert f">{map_name.upper()}</span>" in text
    response = api.get(reverse("training", args=[upload.pk]))
    assert response.status_code == 200
    document = services.training_result(upload.owner, upload.pk)[1]
    expected = export_scenario(document.scenarios[0]).console_line
    assert expected in unescape(response.content.decode())
    assert b'name="rating"' not in response.content
    assert b"?scenario=second-scenario" in response.content
    assert b"?format=cfg" in response.content
    assert f"{map_label(map_name).upper()} / SANDBOX" in response.content.decode()
    assert f"({map_name})" in response.content.decode()
    response = api.get(reverse("practice"))
    assert f"{map_name.upper()} / " in response.content.decode()


def test_report_shows_both_native_locations_for_saved_scenarios(api, completed_upload):
    upload = completed_upload
    report = deepcopy(upload.report)
    first, second = report["scenario_document"]["scenarios"]
    report["scenario_locations"] = {
        first["scenario_id"]: {
            "snapshot_tick": first["source"]["snapshot_tick"],
            "source": "m_szLastPlaceName",
            "player": "TSpawn",
            "opponent": "CTSpawn",
        },
        second["scenario_id"]: {
            "snapshot_tick": second["source"]["snapshot_tick"],
            "source": "m_szLastPlaceName",
            "player": "CTSpawn",
            "opponent": "TSpawn",
        },
    }
    Upload.objects.filter(pk=upload.pk).update(report=report)
    services.save_training_selection(
        upload.owner, upload.pk, {"include": [first["scenario_id"]], "reject": []}
    )
    with patch("cs_map_trainer.parsing.DemoReader", side_effect=AssertionError("No reparse")):
        response = api.get(reverse("report", args=[upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    cards = text.split('<article class="situation"')[1:]
    first_visible = cards[0].split("<details>", 1)[0]
    assert len(cards) == 1
    assert 'class="amber">T Spawn' in first_visible
    assert 'class="cyan">CT Spawn' in first_visible
    assert 'class="amber">CT Spawn' in cards[0]
    assert 'class="cyan">T Spawn' in cards[0]
    assert 'class="matchup"' in first_visible
    assert "Partial legacy selection: 1 / 2 retained" in first_visible
    assert "last named areas reported by the game" in text
    assert "not guessed from coordinates" in text
    assert "before the first damage, not the moment of death" in text
    assert "LOCATION SOURCE m_szLastPlaceName / TICK 100" in text
    assert "PLAYER TSpawn / OPPONENT CTSpawn" in text
    assert "Location data was not recorded" not in text
    assert "Unknown location" not in text
    assert response.context["selected_count"] == 1
    assert [item["choice"] for item in response.context["situations"]] == ["include", "omit"]
    upload.refresh_from_db()
    assert upload.report == report


@pytest.mark.parametrize("missing", ["victim", "killer", "both"])
def test_report_handles_missing_callouts_per_participant(api, completed_upload, missing):
    report = deepcopy(completed_upload.report)
    report["scenario_locations"] = {
        item["scenario_id"]: {
            "snapshot_tick": item["source"]["snapshot_tick"],
            "player": None if missing in {"victim", "both"} else "TSpawn",
            "opponent": None if missing in {"killer", "both"} else "TSpawn",
        }
        for item in report["scenario_document"]["scenarios"]
    }
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 200
    card = response.content.decode().split('<article class="situation"', 1)[1]
    visible, details = card.split("<details>", 1)
    victim_name = "Location unavailable in demo" if missing in {"victim", "both"} else "T Spawn"
    killer_name = "Location unavailable in demo" if missing in {"killer", "both"} else "T Spawn"
    assert f'class="amber">{victim_name}' in visible
    assert f'class="cyan">{killer_name}' in visible
    assert "XYZ " in details
    assert 'type="checkbox" name="group"' in visible
    assert "Location data was not recorded" not in response.content.decode()


def test_legacy_report_does_not_guess_locations_from_coordinates(api, completed_upload):
    report = deepcopy(completed_upload.report)
    report["analysis_version"] = 2
    report.pop("scenario_locations", None)
    for scenario in report["scenario_document"]["scenarios"]:
        # These coordinates were previously labelled T Spawn by the heuristic.
        scenario["player"]["position"] = {"x": 1296.0, "y": -352.0, "z": -144.0}
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    assert 'class="amber">Not recorded in this report' in text
    assert 'class="cyan">Not recorded in this report' in text
    assert "Upload the demo again to include it" in text
    assert 'class="amber">T Spawn' not in text
    assert "Location unavailable in demo" not in text
    assert 'type="checkbox" name="group"' in text


def test_native_location_values_are_escaped_in_labels_and_details(api, completed_upload):
    report = deepcopy(completed_upload.report)
    scenario = report["scenario_document"]["scenarios"][0]
    report["scenario_locations"] = {
        scenario["scenario_id"]: {
            "snapshot_tick": scenario["source"]["snapshot_tick"],
            "player": "<script>alert(1)</script>",
            "opponent": "FuturePlace",
        }
    }
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert 'class="cyan">Future Place' in text


def test_invalid_saved_location_tick_fails_explicitly(api, completed_upload):
    report = deepcopy(completed_upload.report)
    scenario = report["scenario_document"]["scenarios"][0]
    report["scenario_locations"] = {
        scenario["scenario_id"]: {
            "snapshot_tick": scenario["source"]["death_tick"],
            "player": "TSpawn",
            "opponent": "CTSpawn",
        }
    }
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 500
    assert "The saved report is invalid" in response.content.decode()


def test_history_reads_map_without_loading_deferred_reports(api, completed_upload):
    with CaptureQueriesContext(connection) as queries:
        response = api.get(reverse("history"))
    assert response.status_code == 200
    page = list(response.context["page"])
    assert page[0].map_label == map_label(completed_upload.report["map"]["name"])
    assert "report" in page[0].get_deferred_fields()
    upload_reads = [
        query["sql"]
        for query in queries
        if f'FROM "{Upload._meta.db_table}"' in query["sql"] and "COUNT(" not in query["sql"]
    ]
    assert len(upload_reads) == 1
    assert f"{page[0].map_label} /" in response.content.decode()


def test_unfinished_upload_does_not_claim_a_map(api, upload):
    for url in (reverse("report", args=[upload.pk]), reverse("history")):
        response = api.get(url)
        assert response.status_code == 200
        text = response.content.decode()
        assert "Map not yet identified" in text
        assert ">DE_MIRAGE</span>" not in text
        assert ">Mirage /" not in text


@pytest.mark.parametrize(
    "wins, losses, expected_rate",
    [(1, 7, "12.5%"), (0, 1, "0%"), (1, 0, "100%")],
)
def test_group_counts_and_denominator_are_not_skill_score(
    api, completed_upload, wins, losses, expected_rate
):
    upload = completed_upload
    report = upload.report
    report["groups"] = [
        {
            "group_id": "group-a",
            "observations": wins + losses,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / (wins + losses),
            "player_side": "T",
            "player_weapon": "ak47",
            "opponent_weapon": "awp",
            "player_cell": [0, 0, 0],
            "opponent_cell": [1, 1, 0],
            "context_limitations": ["opponent_aim_inferred_toward_player"],
            "selected_scenario_ids": [scenario_id(upload)],
        }
    ]
    Upload.objects.filter(pk=upload.pk).update(report=report)
    response = api.get(reverse("report", args=[upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    assert text.index("Choose your duels") < text.index("Duel statistics")
    statistics = text.split('<details id="duel-statistics">', 1)[1]
    assert "<summary>Duel statistics</summary>" in statistics
    assert "ranked by number of losses" in statistics
    assert "not just your practice selection" in statistics
    assert "not every encounter or your overall performance" in statistics
    assert "Small samples do not support strong conclusions" in statistics
    assert f"<td>{wins + losses}</td>" in statistics
    assert f'<td class="green">{wins}</td><td>{losses}</td>' in statistics
    assert f"<td>{expected_rate}</td>" in statistics
    assert "fraction from 0 to 1" not in text
    summary, technical = statistics.split("<details>", 1)
    assert "T / ak47 vs awp" in summary
    assert "group-a" not in summary
    assert "Player grid cell" not in summary
    assert "<summary>Technical details</summary>" in technical
    assert "group-a" in technical
    assert "Player grid cell" in technical
    assert "opponent_aim_inferred_toward_player" in technical
    upload.refresh_from_db()
    assert upload.report == report


def test_report_prioritizes_selection_and_keeps_raw_data_in_closed_details(api, completed_upload):
    response = api.get(reverse("report", args=[completed_upload.pk]))
    text = response.content.decode()
    assert "Recurring duel setups" not in text
    assert "No comparable groups found." in text
    cards = text.split('<article class="situation"')[1:]
    assert len(cards) == 1
    for card in cards:
        visible, details = card.split("<details>", 1)
        details = details.split("</details>", 1)[0]
        assert "<strong>2 scenarios" in visible
        assert 'type="checkbox" name="group"' in visible
        assert "SCENARIO " not in visible
        assert "SNAPSHOT " not in visible
        assert "XYZ " not in visible
        assert "SCENARIO " in details
        assert "SNAPSHOT " in details
        assert " / DAMAGE " in details
        assert " / DEATH " in details
        assert "XYZ " in details
        assert "PITCH " in details
        assert " / YAW " in details
        assert " / ROLL " in details
    assert '<details class="report-technical"><summary>Technical analysis details</summary>' in text
    assert "Limitations and exclusions" not in text
    assert "Location unavailable" not in text


def test_report_lists_shared_limits_once_and_keeps_scenario_warnings_visible(api, completed_upload):
    report = completed_upload.report
    report["limitations"] = list(BASE_LIMITATIONS)
    first, second = report["scenario_document"]["scenarios"]
    first["limitations"] = [
        *BASE_LIMITATIONS,
        "opponent_aim_inferred_toward_player",
        "player_blinded",
    ]
    second["limitations"] = list(BASE_LIMITATIONS)
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    text = unescape(response.content.decode())
    cards = text.split('<article class="situation"')[1:]
    for card in cards:
        card = card.split("</article>", 1)[0]
        for code in BASE_LIMITATIONS:
            assert code not in card
            assert LIMITATIONS[code] not in card
            assert text.count(LIMITATIONS[code]) == 1
    warning_card = next(card for card in cards if "player_blinded" in card)
    other_card = next(card for card in cards if "player_blinded" not in card)
    first_visible, first_details = warning_card.split("<details>", 1)
    for code in ("opponent_aim_inferred_toward_player", "player_blinded"):
        assert limitation_short(code) in first_visible
        assert code not in first_visible
        assert code in first_details
        assert LIMITATIONS[code] not in other_card.split("</article>", 1)[0]
    assert 'class="scenario-warnings warning"' not in other_card.split("</article>", 1)[0]


def test_report_preserves_shared_limits_missing_from_report_metadata(api, completed_upload):
    response = api.get(reverse("report", args=[completed_upload.pk]))
    text = response.content.decode()
    shared = text.split("<summary>Technical analysis details</summary>", 1)[1]
    shared = shared.split("</details>", 1)[0]
    assert "map_geometry_unverified" in shared
    assert LIMITATIONS["map_geometry_unverified"] in shared


def test_wins_only_report_keeps_statistics_without_training_controls(api, completed_upload):
    report = completed_upload.report
    report.update(
        status="no_eligible_duels",
        scenario_document=None,
        eligible_candidates=0,
        kills_considered=1,
        eligible_wins=1,
    )
    report["groups"] = [
        {
            "group_id": "win-only",
            "observations": 1,
            "wins": 1,
            "losses": 0,
            "win_rate": 1.0,
            "player_side": "T",
            "player_weapon": "ak47",
            "opponent_weapon": "awp",
            "player_cell": [0, 0, 0],
            "opponent_cell": [1, 1, 0],
            "context_limitations": [],
            "selected_scenario_ids": [],
        }
    ]
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 200
    text = response.content.decode()
    assert "No practice candidates found" in text
    assert '<details id="duel-statistics">' in text
    assert "win-only" in text
    assert "<td>100%</td>" in text
    assert "Choose your duels" not in text
    assert "Save selection" not in text
    assert "Open practice" not in text


def test_empty_report_has_no_export_or_selection(api, completed_upload):
    report = completed_upload.report
    report.update(status="no_eligible_duels", scenario_document=None, eligible_candidates=0)
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 200
    assert "No practice candidates found" in response.content.decode()
    assert b"Save selection" not in response.content
    assert api.get(reverse("training", args=[completed_upload.pk])).status_code == 409
    assert practice.practice_queue(completed_upload.owner, "due") == []


def test_report_metadata_and_invalid_json_fail_explicitly(api, completed_upload):
    url = reverse("report", args=[completed_upload.pk])
    Upload.objects.filter(pk=completed_upload.pk).update(report={"invalid": True})
    assert api.get(url).status_code == 500
    assert b"invalid_saved_report" in api.get(url).content


def test_missing_document_is_not_presented_as_successful_empty_analysis(api, completed_upload):
    report = completed_upload.report
    report["scenario_document"] = None
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert response.status_code == 500
    assert b"invalid_saved_report" in response.content


def test_report_content_is_escaped(api, completed_upload):
    report = completed_upload.report
    report["limitations"] = ['<script>alert("demo")</script>']
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("report", args=[completed_upload.pk]))
    assert b"&lt;script&gt;" in response.content
    assert b'<script>alert("demo")</script>' not in response.content


def test_selection_form_persists_and_training_respects_it(api, completed_upload):
    upload = completed_upload
    response = api.post(
        reverse("selection", args=[upload.pk]),
        {
            f"choice_{scenario_id(upload)}": "reject",
            "choice_second-scenario": "include",
        },
    )
    assert response.status_code == 302
    upload.refresh_from_db()
    assert upload.selection == {"include": ["second-scenario"], "reject": [scenario_id(upload)]}
    response = api.get(reverse("training", args=[upload.pk]))
    assert response.context["current"].scenario_id == "second-scenario"
    assert (
        api.get(
            reverse("training", args=[upload.pk]), {"scenario": scenario_id(upload)}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("choice", ["omit", "reject", "injected"])
def test_empty_or_invalid_form_preserves_previous_selection(api, completed_upload, choice):
    response = api.post(
        reverse("selection", args=[completed_upload.pk]),
        {
            f"choice_{scenario_id(completed_upload)}": choice,
            "choice_second-scenario": choice,
        },
    )
    assert response.status_code == 400
    completed_upload.refresh_from_db()
    assert completed_upload.selection is None


def test_unexportable_scenario_is_not_hidden(api, completed_upload):
    report = completed_upload.report
    report["scenario_document"]["scenarios"][0]["player"]["view_angles"]["roll"] = 1.0
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    response = api.get(reverse("training", args=[completed_upload.pk]))
    assert response.status_code == 200
    assert "cannot be exported" in response.content.decode()
    assert b'id="copy-command"' not in response.content


@pytest.mark.parametrize("rating,days", [("hard", 1), ("done", 3), ("easy", 7)])
def test_schedule_is_server_timed_and_updates_one_record(completed_upload, rating, days):
    now = timezone.now()
    with patch("cs_map_trainer.web.practice.timezone.now", return_value=now):
        first = rate(completed_upload, rating)
        assert first.reviewed_at == now
        assert first.due_at == now + timedelta(days=days)
    later = now + timedelta(hours=2)
    with patch("cs_map_trainer.web.practice.timezone.now", return_value=later):
        second = rate(completed_upload, rating)
    assert first.pk == second.pk
    assert second.due_at == later + timedelta(days=days)
    assert completed_upload.practice_reviews.count() == 1


def test_irrelevant_and_restore_do_not_modify_pack_selection(completed_upload):
    original = services.get_training_selection(completed_upload.owner, completed_upload.pk)
    review = rate(completed_upload, "irrelevant")
    assert review.due_at is None
    assert len(practice.practice_queue(completed_upload.owner, "due")) == 1
    assert len(practice.practice_queue(completed_upload.owner, "dismissed")) == 1
    practice.review_scenario(
        completed_upload.owner, completed_upload.pk, scenario_id(completed_upload), "restore"
    )
    assert not completed_upload.practice_reviews.exists()
    assert len(practice.practice_queue(completed_upload.owner, "due")) == 2
    assert services.get_training_selection(completed_upload.owner, completed_upload.pk) == original


def test_due_boundary_and_latest_choice_are_respected(completed_upload):
    review = rate(completed_upload, "hard")
    with patch("cs_map_trainer.web.practice.timezone.now", return_value=review.due_at):
        assert len(practice.practice_queue(completed_upload.owner, "due")) == 2
    with patch(
        "cs_map_trainer.web.practice.timezone.now",
        return_value=review.due_at - timedelta(seconds=1),
    ):
        assert len(practice.practice_queue(completed_upload.owner, "upcoming")) == 1
    services.save_training_selection(
        completed_upload.owner,
        completed_upload.pk,
        {"include": ["second-scenario"], "reject": []},
    )
    assert practice.practice_queue(completed_upload.owner, "upcoming") == []
    assert completed_upload.practice_reviews.count() == 1


@pytest.mark.parametrize("rating", ["", "won", None, ["easy"], True])
def test_invalid_rating_does_not_write(completed_upload, rating):
    with pytest.raises(services.IntakeError, match="invalid_practice_rating"):
        rate(completed_upload, rating)
    assert not completed_upload.practice_reviews.exists()


def test_review_id_and_ready_state_are_validated(completed_upload):
    with pytest.raises(services.IntakeError, match="scenario_not_found"):
        practice.review_scenario(completed_upload.owner, completed_upload.pk, "unknown", "easy")
    Upload.objects.filter(pk=completed_upload.pk).update(state="running")
    with pytest.raises(services.IntakeError, match="result_not_ready"):
        rate(completed_upload, "easy")


def test_queue_validates_report_document_consistency(completed_upload):
    report = completed_upload.report
    report["scenario_document"]["scenarios"][0]["map"]["game_build"] += 1
    Upload.objects.filter(pk=completed_upload.pk).update(report=report)
    with pytest.raises(services.IntakeError, match="invalid_saved_report"):
        practice.practice_queue(completed_upload.owner, "due")


def test_review_database_constraints(completed_upload):
    first = rate(completed_upload, "easy")
    with pytest.raises(IntegrityError), transaction.atomic():
        PracticeReview.objects.create(
            upload=completed_upload,
            scenario_id=first.scenario_id,
            rating="easy",
            reviewed_at=timezone.now(),
            due_at=timezone.now(),
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PracticeReview.objects.filter(pk=first.pk).update(rating="irrelevant")


def test_review_form_redirect_and_read_only_get(api, completed_upload):
    response = api.post(review_url(completed_upload), {"rating": "hard"})
    assert response.status_code == 302
    assert response.url == "/practice/"
    assert api.get(review_url(completed_upload)).status_code == 405
    assert b"hard" not in api.get("/practice/?filter=upcoming").content
    assert ">Hard<" not in api.get("/practice/?filter=upcoming").content.decode()
    assert api.get("/practice/?filter=unknown").status_code == 200
    assert api.get("/practice/").context["page"].paginator.count == 1
    assert completed_upload.practice_reviews.get().rating == "hard"


@pytest.mark.parametrize(
    "operation", ["report", "training", "review", "selection", "remove_upload"]
)
def test_other_users_cannot_access_private_surfaces(client, completed_upload, operation):
    other = get_user_model().objects.create_user("other", "other@example.test", "some-password")
    EmailAddress.objects.create(user=other, email=other.email, primary=True, verified=True)
    client.force_login(other)
    args = [completed_upload.pk]
    if operation == "review":
        args.append(scenario_id(completed_upload))
    url = reverse(operation, args=args)
    response = (
        client.get(url)
        if operation in {"report", "training"}
        else client.post(url, {"rating": "easy", "confirm": "yes"})
    )
    assert response.status_code == 404
    assert "no-store" in response["Cache-Control"]
    assert practice.practice_queue(other, "due") == []
    assert not completed_upload.practice_reviews.exists()


@pytest.mark.parametrize("operation", ["review", "selection", "remove_upload", "remove_account"])
def test_ui_mutations_require_csrf(user, completed_upload, operation):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    args = [] if operation == "remove_account" else [completed_upload.pk]
    if operation == "review":
        args.append(scenario_id(completed_upload))
    response = client.post(reverse(operation, args=args), {"rating": "easy", "confirm": "yes"})
    assert response.status_code == 403
    assert not completed_upload.practice_reviews.exists()


def test_soft_delete_erases_practice_state_and_prevents_access(api, completed_upload):
    rate(completed_upload, "hard")
    url = reverse("remove_upload", args=[completed_upload.pk])
    assert api.post(url).status_code == 400
    response = api.post(url, {"confirm": "yes"})
    assert response.status_code == 302
    assert not PracticeReview.objects.exists()
    assert api.get(reverse("report", args=[completed_upload.pk])).status_code == 404
    assert api.get(reverse("training", args=[completed_upload.pk])).status_code == 404
    assert api.post(review_url(completed_upload), {"rating": "hard"}).status_code == 404
    assert practice.practice_queue(completed_upload.owner, "due") == []


def test_delete_account_requires_password_and_erases_reviews(api, completed_upload):
    rate(completed_upload, "easy")
    assert api.post("/account/delete/", {"confirm": "yes", "password": "bad"}).status_code == 403
    assert PracticeReview.objects.count() == 1
    assert (
        api.post("/account/delete/", {"confirm": "yes", "password": "some-password"}).status_code
        == 302
    )
    assert not PracticeReview.objects.exists()
    completed_upload.refresh_from_db()
    assert completed_upload.owner is None
    assert completed_upload.report is None


def test_direct_user_delete_also_erases_reviews(completed_upload):
    rate(completed_upload, "easy")
    completed_upload.owner.delete()
    assert not PracticeReview.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_account_deletion_cannot_leave_concurrently_created_review(completed_upload):
    updating_uploads = Event()
    user_id = completed_upload.owner_id

    def deleting():
        def watch_update(execute, sql, params, many, context):
            if sql.startswith('UPDATE "trainer_upload"'):
                updating_uploads.set()
            return execute(sql, params, many, context)

        try:
            with connection.execute_wrapper(watch_update):
                get_user_model().objects.get(pk=user_id).delete()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=completed_upload.pk)
            future = pool.submit(deleting)
            assert updating_uploads.wait(10)
            rate(completed_upload, "hard")
        future.result(timeout=10)
    assert not PracticeReview.objects.exists()
    completed_upload.refresh_from_db()
    assert completed_upload.owner_id is None


def test_browser_navigation_errors_are_html_but_fetch_errors_stay_json(api, settings):
    data = {
        "request_id": str(uuid.uuid4()),
        "size_bytes": 32,
        "has_upload_rights": True,
        "player_steam_id": "76561198000000001",
    }
    settings.R2_BUCKET = ""
    response = api.post(
        "/backend/uploads/", data, content_type="application/json", HTTP_ACCEPT="text/html"
    )
    assert response.status_code == 503
    assert b"trainer/app.css" in response.content
    assert b"storage_not_configured" in response.content
    response = api.post(
        "/backend/uploads/",
        data,
        content_type="application/json",
    )
    assert response.status_code == 503
    assert response.json() == {"error": "storage_not_configured"}
    assert not Upload.objects.exists()


def test_active_upload_cannot_be_deleted(api, upload):
    response = api.post(reverse("remove_upload", args=[upload.pk]), {"confirm": "yes"})
    assert response.status_code == 409
    response = api.post("/account/delete/", {"confirm": "yes", "password": "some-password"})
    assert response.status_code == 409


def test_history_and_queue_include_older_than_100_reports(api, completed_upload):
    upload = completed_upload
    now = timezone.now()
    for _index in range(102):
        Upload.objects.create(
            owner=upload.owner,
            player_steam_id=upload.player_steam_id,
            request_id=uuid.uuid4(),
            size_bytes=32,
            key=f"inputs/{uuid.uuid4()}.dem",
            expires_at=now,
            state="ready",
            report=upload.report,
            cleanup_pending=False,
        )
    response = api.get("/history/")
    assert response.context["page"].paginator.count == 103
    response = api.get("/practice/")
    assert response.context["page"].paginator.count == 103
    assert len(response.context["page"]) == 20
    entries = practice.practice_queue(upload.owner, "due")
    assert entries[0]["upload"].pk == upload.pk
    response = api.get("/practice/?page=2&filter=due")
    assert b"filter=due" not in response.content
    assert response.context["page"].number == 2
