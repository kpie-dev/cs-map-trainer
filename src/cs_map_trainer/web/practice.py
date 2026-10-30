"""User-declared practice state; no game telemetry or automatic completion."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import PracticeReview, Upload
from .services import (
    IntakeError,
    saved_selection,
    training_document,
    training_result,
    validated_report,
)

INTERVALS = {"hard": 1, "done": 3, "easy": 7}


@transaction.atomic
def review_scenario(user, upload_id, scenario_id, rating):
    upload, document = training_result(user, upload_id, lock=True)
    if not any(item.scenario_id == scenario_id for item in document.scenarios):
        raise IntakeError("scenario_not_found", 404)
    if not isinstance(rating, str) or rating not in {*PracticeReview.Rating.values, "restore"}:
        raise IntakeError("invalid_practice_rating", 400)
    if rating == "restore":
        upload.practice_reviews.filter(scenario_id=scenario_id).delete()
        return
    now = timezone.now()
    PracticeReview.objects.update_or_create(
        upload=upload,
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
    uploads = (
        Upload.objects.filter(owner=user, state=Upload.State.READY)
        .defer("scripts")
        .prefetch_related("practice_reviews")
        .order_by("created_at", "id")
    )
    for upload in uploads:
        report = validated_report(upload)
        if report.status == "no_eligible_duels" and report.scenario_document is None:
            continue
        document = training_document(upload, report)
        _, selected = saved_selection(upload, document)
        reviews = {item.scenario_id: item for item in upload.practice_reviews.all()}
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
