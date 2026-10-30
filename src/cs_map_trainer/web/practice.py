"""User-declared practice state; no game telemetry or automatic completion."""

from copy import copy
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from cs_map_trainer.training_groups import practice_priority

from .grouping import present_groups
from .models import PracticeReview, Upload
from .services import (
    IntakeError,
    attach_player,
    saved_selection,
    training_document,
    training_result,
    validated_report,
)

INTERVALS = {"hard": 1, "done": 3, "easy": 7}


def ready_player_uploads(user):
    uploads = (
        Upload.objects.filter(owner=user, state=Upload.State.READY)
        .defer("scripts")
        .prefetch_related("player_results", "practice_reviews")
        .order_by("created_at", "id")
    )
    for upload in uploads.iterator(chunk_size=100):
        for result in list(upload.player_results.all()) or [None]:
            if result and result.status == "missing":
                continue
            selected = copy(upload)
            attach_player(selected, result.steam_id if result else None)
            yield selected


@transaction.atomic
def review_scenario(user, upload_id, scenario_id, rating, *, steam_id=None):
    upload, document = training_result(user, upload_id, lock=True, steam_id=steam_id)
    if not any(item.scenario_id == scenario_id for item in document.scenarios):
        raise IntakeError("scenario_not_found", 404)
    if not isinstance(rating, str) or rating not in {*PracticeReview.Rating.values, "restore"}:
        raise IntakeError("invalid_practice_rating", 400)
    result = upload.analysis_result
    if result and result.report is None:
        result = None
    if rating == "restore":
        upload.practice_reviews.filter(player_result=result, scenario_id=scenario_id).delete()
        return
    now = timezone.now()
    PracticeReview.objects.update_or_create(
        upload=upload,
        player_result=result,
        scenario_id=scenario_id,
        defaults={
            "rating": rating,
            "reviewed_at": now,
            "due_at": now + timedelta(days=INTERVALS[rating]) if rating in INTERVALS else None,
        },
    )


def practice_queue(user, category):
    if category not in {"due", "upcoming", "dismissed"}:
        raise IntakeError("invalid_practice_filter", 400)
    now = timezone.now()
    entries = []
    for upload in ready_player_uploads(user):
        report = validated_report(upload)
        if report.status == "no_eligible_duels" and report.scenario_document is None:
            continue
        document = training_document(upload, report)
        _, selected = saved_selection(upload, document)
        result = upload.analysis_result
        reviews = {
            item.scenario_id: item
            for item in upload.practice_reviews.all()
            if item.player_result_id == (result.pk if result and result.report else None)
        }
        for scenario in selected.scenarios:
            review = reviews.get(scenario.scenario_id)
            if review and review.rating == PracticeReview.Rating.IRRELEVANT:
                bucket = "dismissed"
            elif review and review.due_at > now:
                bucket = "upcoming"
            else:
                bucket = "due"
            if bucket == category:
                entries.append(
                    {
                        "upload": upload,
                        "scenario": scenario,
                        "review": review,
                        "sort_at": review.due_at if review and review.due_at else upload.created_at,
                    }
                )
    return sorted(
        entries,
        key=lambda item: (item["sort_at"], str(item["upload"].pk), item["scenario"].scenario_id),
    )


def practice_library(user):
    """Selected scenarios from every ready report, independent of legacy reviews."""
    entries = []
    for upload in ready_player_uploads(user):
        result = upload.analysis_result
        report = validated_report(upload)
        if report.status == "no_eligible_duels" and report.scenario_document is None:
            continue
        document = training_document(upload, report)
        _, selected = saved_selection(upload, document)
        steam_id = result.steam_id if result else upload.player_steam_id
        prefix = f"/uploads/{upload.pk}/"
        if upload.mode == "team":
            prefix += f"players/{steam_id}/"
        entries.extend(
            {
                "upload": upload,
                "scenario": group["first"]["scenario"],
                "group": group,
                "steam_id": steam_id,
                "player_name": result.name if result else "",
                "team": upload.mode == "team",
                "training_url": prefix + "training/",
            }
            for group in present_groups(report, {s.scenario_id for s in selected.scenarios})
            if group["selected"]
        )
    team_library = any(item["team"] for item in entries)
    return sorted(
        entries,
        key=lambda item: (
            item["steam_id"] if team_library else "",
            practice_priority(item["scenario"]),
            item["upload"].created_at,
            str(item["upload"].pk),
            item["group"]["group_id"],
        ),
    )
