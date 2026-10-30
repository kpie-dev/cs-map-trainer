import json
import logging
import re
import uuid
from datetime import UTC, timedelta

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_q.tasks import async_task
from pydantic import ValidationError

from cs_map_trainer.analysis import AnalysisReport
from cs_map_trainer.exporting import ExportError, export_scenario
from cs_map_trainer.packs import build_pack, load_scenarios, select_scenarios
from cs_map_trainer.scenarios import ContractModel, Identifier
from cs_map_trainer.training_groups import expand_group_selection

from .entitlements import coach_access, monthly_limit, pro_access
from .identity import lock_account
from .models import AccountPreferences, PlayerAnalysis, Upload
from .storage import R2, InvalidUpload

logger = logging.getLogger(__name__)
ACTIVE = (Upload.State.UPLOADING, Upload.State.QUEUED, Upload.State.RUNNING)
TERMINAL = (
    Upload.State.READY,
    Upload.State.UNSUPPORTED,
    Upload.State.FAILED,
    Upload.State.EXPIRED,
    Upload.State.DELETED,
)


class IntakeError(ValueError):
    def __init__(self, code, status=409, *, scenario_ids=None):
        self.code = code
        self.status = status
        self.scenario_ids = scenario_ids or []
        super().__init__(code)


def month_start(now=None):
    return (
        (now or timezone.now())
        .astimezone(UTC)
        .replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )


def quota_used(user):
    return (
        Upload.objects.filter(owner=user, quota_charged=True)
        .annotate(quota_at=Coalesce("accepted_at", "created_at"))
        .filter(quota_at__gte=month_start())
        .count()
    )


def validate_player_steam_id(player_steam_id):
    if not isinstance(player_steam_id, str) or not re.fullmatch(
        r"[0-9]{17}", player_steam_id.strip()
    ):
        raise IntakeError("invalid_player_steam_id", 400)
    return player_steam_id.strip()


def initiate(user, request_id, size, player_steam_id=None, storage=None, *, mode="individual"):
    if type(size) is not int or not 8 <= size <= 1024**3:
        raise IntakeError("invalid_demo_size", 400)
    if mode not in {"individual", "team"}:
        raise IntakeError("invalid_analysis_mode", 400)
    if mode == "individual":
        player_steam_id = validate_player_steam_id(player_steam_id)
    elif player_steam_id is not None:
        raise IntakeError("invalid_team_roster", 400)
    storage = storage or R2()
    now = timezone.now()
    with transaction.atomic():
        user = lock_account(user)
        if not user.is_active:
            raise IntakeError("account_blocked", 403)
        existing = Upload.objects.filter(owner=user, request_id=request_id).first()
        if existing:
            if (
                existing.size_bytes != size
                or existing.mode != mode
                or (mode == "individual" and existing.player_steam_id != player_steam_id)
            ):
                raise IntakeError("idempotency_conflict")
            return existing
        if mode == "team":
            from .teams import roster_members

            if not coach_access(user):
                raise IntakeError("coach_required", 403)
            members = list(roster_members(user))
            if not 1 <= len(members) <= 5:
                raise IntakeError("team_roster_required", 400)
            players = [(member.steam_id, member.name) for member in members]
        else:
            players = [(player_steam_id, "")]
        if Upload.objects.filter(owner=user, state__in=ACTIVE).exists():
            raise IntakeError("active_upload_exists")
        if Upload.objects.filter(owner=user, state__in=TERMINAL, cleanup_pending=True).exists():
            raise IntakeError("input_cleanup_pending", 503)
        used = quota_used(user)
        if used >= monthly_limit(user) and not pro_access(user):
            raise IntakeError("monthly_demo_limit", 429)
        upload = Upload(
            owner=user,
            mode=mode,
            player_steam_id=players[0][0],
            request_id=request_id,
            size_bytes=size,
            key=f"inputs/{uuid.uuid4()}.dem",
            expires_at=now + timedelta(seconds=settings.UPLOAD_EXPIRE_SECONDS),
        )
        upload.save()
        PlayerAnalysis.objects.bulk_create(
            PlayerAnalysis(upload=upload, steam_id=steam_id, name=name, position=position)
            for position, (steam_id, name) in enumerate(players)
        )
        upload.multipart_id = storage.begin(upload)
        upload.save(update_fields=["multipart_id"])
        if mode == "individual":
            AccountPreferences.objects.update_or_create(
                owner=user, defaults={"last_player_steam_id": player_steam_id}
            )
    return upload


def complete(user, upload_id, storage=None):
    storage = storage or R2()
    with transaction.atomic():
        user = lock_account(user)
        if not user.is_active:
            raise IntakeError("account_blocked", 403)
        upload = Upload.objects.select_for_update().get(pk=upload_id, owner=user)
        if upload.state != Upload.State.UPLOADING:
            return upload
        if upload.expires_at <= timezone.now():
            raise IntakeError("upload_expired", 410)
        try:
            try:
                storage.complete(upload)
            except ClientError as error:
                # Completion may have committed in R2 before the database transaction failed.
                if error.response["Error"]["Code"] != "NoSuchUpload":
                    raise
                storage.verify(upload)
        except InvalidUpload as error:
            raise IntakeError("invalid_uploaded_object", 400) from error
        upload.state = Upload.State.QUEUED
        upload.accepted_at = timezone.now()
        upload.save(update_fields=["state", "accepted_at"])
        transaction.on_commit(lambda: dispatch(upload.pk))
    return upload


def dispatch(upload_id):
    try:
        async_task("cs_map_trainer.web.tasks.process_upload", str(upload_id))
    except Exception:
        # A committed queued row is the durable outbox, including a lost acknowledgement.
        logger.exception("Could not enqueue upload %s; maintenance will redispatch", upload_id)
        return
    Upload.objects.filter(pk=upload_id, state=Upload.State.QUEUED).update(
        dispatched_at=timezone.now()
    )


def delete_history(user, upload_id):
    with transaction.atomic():
        upload = Upload.objects.select_for_update().get(pk=upload_id, owner=user)
        if upload.state in ACTIVE:
            raise IntakeError("processing_in_progress")
        upload.state = Upload.State.DELETED
        upload.report = None
        upload.scripts = None
        upload.selection = None
        upload.save(update_fields=["state", "report", "scripts", "selection"])
        upload.practice_reviews.all().delete()
        upload.player_results.all().delete()


def delete_account(user):
    from .billing import close_account

    with transaction.atomic():
        lock_account(user)
        if Upload.objects.filter(owner=user, state__in=ACTIVE).exists():
            raise IntakeError("processing_in_progress")
        close_account(user)
        user.delete()


STORAGE_ERRORS = (BotoCoreError, ClientError, OSError, TimeoutError)


class TrainingSelection(ContractModel):
    include: list[Identifier] | None
    reject: list[Identifier]


def attach_player(upload, steam_id=None, *, lock=False):
    results = upload.player_results.all()
    if lock:
        results = results.select_for_update()
    if steam_id is None:
        if upload.mode == "team":
            raise IntakeError("player_required", 400)
        result = results.first()
    else:
        if not isinstance(steam_id, str) or not re.fullmatch(r"[0-9]{17}", steam_id):
            raise IntakeError("invalid_player_steam_id", 400)
        result = results.filter(steam_id=steam_id).first()
        if result is None:
            raise IntakeError("player_not_found", 404)
    upload.analysis_result = result
    if result:
        if result.status == "missing":
            raise IntakeError("player_not_in_demo", 409)
        if result.report is not None or upload.mode == "team":
            upload.report = result.report
            upload.scripts = result.scripts
            upload.selection = result.selection
        upload.player_steam_id = result.steam_id
    return upload


def validated_report(upload):
    if not hasattr(upload, "analysis_result"):
        attach_player(upload)
    try:
        report = AnalysisReport.model_validate_json(json.dumps(upload.report))
    except (ValueError, TypeError) as error:
        logger.error("Invalid saved training report for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500) from error
    if report.player_steam_id != upload.player_steam_id:
        logger.error("Saved report player mismatch for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500)
    if report.scenario_document and any(
        scenario.player.steam_id != upload.player_steam_id
        for scenario in report.scenario_document.scenarios
    ):
        logger.error("Saved scenario player mismatch for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500)
    if (report.status == "candidates_ready") != (report.scenario_document is not None):
        logger.error("Saved report status/document mismatch for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500)
    return report


def training_result(user, upload_id, *, lock=False, steam_id=None):
    uploads = Upload.objects.exclude(state=Upload.State.DELETED)
    if lock:
        uploads = uploads.select_for_update()
    upload = uploads.get(pk=upload_id, owner=user)
    if upload.state != Upload.State.READY:
        raise IntakeError("result_not_ready")
    attach_player(upload, steam_id, lock=lock)
    report = validated_report(upload)
    return upload, training_document(upload, report)


def training_document(upload, report):
    if report.status == "no_eligible_duels" and report.scenario_document is None:
        raise IntakeError("no_training_candidates")
    try:
        document = load_scenarios(report.model_dump_json().encode("utf-8"))
    except (ValidationError, ExportError) as error:
        logger.error("Invalid saved training candidates for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500) from error
    return document


def saved_selection(upload, document):
    try:
        selection = (
            TrainingSelection(include=None, reject=[])
            if upload.selection is None
            else TrainingSelection.model_validate(upload.selection)
        )
        selected = select_scenarios(document, include=selection.include, reject=selection.reject)
    except (ValidationError, ExportError) as error:
        logger.error("Invalid saved training selection for upload %s", upload.pk)
        raise IntakeError("invalid_saved_selection", 500) from error
    return selection, selected


def selection_result(document, selection, selected):
    return {
        **selection.model_dump(),
        "available_scenario_ids": [item.scenario_id for item in document.scenarios],
        "selected_scenario_ids": [item.scenario_id for item in selected.scenarios],
        "compatibility": "unverified_in_game",
    }


def get_training_selection(user, upload_id, *, steam_id=None):
    upload, document = training_result(user, upload_id, steam_id=steam_id)
    selection, selected = saved_selection(upload, document)
    return selection_result(document, selection, selected)


@transaction.atomic
def save_training_selection(user, upload_id, data, *, steam_id=None):
    upload, document = training_result(user, upload_id, lock=True, steam_id=steam_id)
    selection, selected = validate_training_selection(document, data)
    upload.selection = selection.model_dump()
    persist_selection(upload)
    return selection_result(document, selection, selected)


def validate_training_selection(document, data):
    try:
        selection = TrainingSelection.model_validate(data)
    except ValidationError as error:
        raise IntakeError("invalid_selection_payload", 400) from error
    try:
        selected = select_scenarios(document, include=selection.include, reject=selection.reject)
    except ExportError as error:
        raise IntakeError("invalid_scenario_selection", 400) from error
    return selection, selected


@transaction.atomic
def persist_selection(upload):
    result = upload.analysis_result
    if result and result.report is not None:
        result.selection = upload.selection
        result.save(update_fields=["selection"])
    else:
        upload.save(update_fields=["selection"])


@transaction.atomic
def submit_training_selection(user, upload_id, included, *, download, partial=None, steam_id=None):
    """Build and persist one locked snapshot, retaining historical rejections."""
    upload, document = training_result(user, upload_id, lock=True, steam_id=steam_id)
    previous, _ = saved_selection(upload, document)
    if partial is not None:
        try:
            included = expand_group_selection(document, included, partial)
        except (ValueError, TypeError) as error:
            raise IntakeError("invalid_selection_payload", 400) from error
    selection, selected = validate_training_selection(
        document,
        {"include": included, "reject": [sid for sid in previous.reject if sid not in included]},
    )
    pack = None
    if download:
        failed = []
        for scenario in selected.scenarios:
            try:
                export_scenario(scenario)
            except ExportError:
                failed.append(scenario.scenario_id)
        if failed:
            raise IntakeError("scenario_not_exportable", 422, scenario_ids=failed)
        pack = build_training_pack(document, selection, include_cfg=True)
    upload.selection = selection.model_dump()
    persist_selection(upload)
    return pack


def training_pack(user, upload_id, *, include_cfg=False, steam_id=None):
    upload, document = training_result(user, upload_id, steam_id=steam_id)
    selection, _ = saved_selection(upload, document)
    return build_training_pack(document, selection, include_cfg=include_cfg)


def build_training_pack(document, selection, *, include_cfg):
    try:
        return build_pack(
            document,
            include=selection.include,
            reject=selection.reject,
            include_cfg=include_cfg,
        )
    except ExportError as error:
        raise IntakeError("scenario_not_exportable", 422) from error


def training_export(user, upload_id, scenario_id, *, steam_id=None):
    _, document = training_result(user, upload_id, steam_id=steam_id)
    scenario = next((item for item in document.scenarios if item.scenario_id == scenario_id), None)
    if scenario is None:
        raise IntakeError("scenario_not_found", 404)
    try:
        return scenario, export_scenario(scenario)
    except ExportError as error:
        raise IntakeError("scenario_not_exportable", 422) from error
