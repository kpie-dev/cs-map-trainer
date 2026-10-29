import json
import logging
import uuid
from datetime import timedelta

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

from .models import SteamIdentity, Upload
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
    def __init__(self, code, status=409):
        self.code = code
        self.status = status
        super().__init__(code)


def initiate(user, request_id, size, storage=None):
    if type(size) is not int or not 8 <= size <= 1024**3:
        raise IntakeError("invalid_demo_size", 400)
    storage = storage or R2()
    now = timezone.now()
    with transaction.atomic():
        try:
            identity = SteamIdentity.objects.select_for_update().get(owner=user)
        except SteamIdentity.DoesNotExist as error:
            raise IntakeError("verified_steam_required", 403) from error
        existing = Upload.objects.filter(identity=identity, request_id=request_id).first()
        if existing:
            if existing.size_bytes != size:
                raise IntakeError("idempotency_conflict")
            return existing
        if Upload.objects.filter(identity=identity, state__in=ACTIVE).exists():
            raise IntakeError("active_upload_exists")
        if Upload.objects.filter(
            identity=identity, state__in=TERMINAL, cleanup_pending=True
        ).exists():
            raise IntakeError("input_cleanup_pending", 503)
        used = (
            Upload.objects.filter(identity=identity, quota_charged=True)
            .annotate(quota_at=Coalesce("accepted_at", "created_at"))
            .filter(quota_at__gt=now - timedelta(days=7))
            .count()
        )
        if used >= settings.DEMO_WEEKLY_LIMIT:
            raise IntakeError("weekly_demo_limit", 429)
        upload = Upload(
            owner=user,
            identity=identity,
            request_id=request_id,
            size_bytes=size,
            key=f"inputs/{uuid.uuid4()}.dem",
            expires_at=now + timedelta(seconds=settings.UPLOAD_EXPIRE_SECONDS),
        )
        upload.save()
        upload.multipart_id = storage.begin(upload)
        upload.save(update_fields=["multipart_id"])
    return upload


def complete(user, upload_id, storage=None):
    storage = storage or R2()
    with transaction.atomic():
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


def delete_account(user):
    with transaction.atomic():
        identity = SteamIdentity.objects.select_for_update().filter(owner=user).first()
        if identity and Upload.objects.filter(identity=identity, state__in=ACTIVE).exists():
            raise IntakeError("processing_in_progress")
        user.delete()


STORAGE_ERRORS = (BotoCoreError, ClientError, OSError, TimeoutError)


class TrainingSelection(ContractModel):
    include: list[Identifier] | None
    reject: list[Identifier]


def training_result(user, upload_id, *, lock=False):
    uploads = Upload.objects.exclude(state=Upload.State.DELETED)
    if lock:
        uploads = uploads.select_for_update()
    upload = uploads.get(pk=upload_id, owner=user)
    if upload.state != Upload.State.READY:
        raise IntakeError("result_not_ready")
    try:
        raw = json.dumps(upload.report)
        report = AnalysisReport.model_validate_json(raw)
    except (ValueError, TypeError) as error:
        logger.error("Invalid saved training report for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500) from error
    if report.player_steam_id != upload.identity_id:
        logger.error("Saved report player mismatch for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500)
    if report.status == "no_eligible_duels" and report.scenario_document is None:
        raise IntakeError("no_training_candidates")
    try:
        document = load_scenarios(raw.encode("utf-8"))
    except (ValidationError, ExportError) as error:
        logger.error("Invalid saved training candidates for upload %s", upload.pk)
        raise IntakeError("invalid_saved_report", 500) from error
    return upload, document


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


def get_training_selection(user, upload_id):
    upload, document = training_result(user, upload_id)
    selection, selected = saved_selection(upload, document)
    return selection_result(document, selection, selected)


@transaction.atomic
def save_training_selection(user, upload_id, data):
    upload, document = training_result(user, upload_id, lock=True)
    try:
        selection = TrainingSelection.model_validate(data)
    except ValidationError as error:
        raise IntakeError("invalid_selection_payload", 400) from error
    try:
        selected = select_scenarios(document, include=selection.include, reject=selection.reject)
    except ExportError as error:
        raise IntakeError("invalid_scenario_selection", 400) from error
    upload.selection = selection.model_dump()
    upload.save(update_fields=["selection"])
    return selection_result(document, selection, selected)


def training_pack(user, upload_id, *, include_cfg=False):
    upload, document = training_result(user, upload_id)
    selection, _ = saved_selection(upload, document)
    try:
        return build_pack(
            document,
            include=selection.include,
            reject=selection.reject,
            include_cfg=include_cfg,
        )
    except ExportError as error:
        raise IntakeError("scenario_not_exportable", 422) from error


def training_export(user, upload_id, scenario_id):
    _, document = training_result(user, upload_id)
    scenario = next((item for item in document.scenarios if item.scenario_id == scenario_id), None)
    if scenario is None:
        raise IntakeError("scenario_not_found", 404)
    try:
        return scenario, export_scenario(scenario)
    except ExportError as error:
        raise IntakeError("scenario_not_exportable", 422) from error
