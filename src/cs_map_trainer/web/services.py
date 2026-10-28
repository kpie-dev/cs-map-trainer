import logging
import uuid
from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_q.tasks import async_task

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
        upload.save(update_fields=["state", "report", "scripts"])


def delete_account(user):
    with transaction.atomic():
        identity = SteamIdentity.objects.select_for_update().filter(owner=user).first()
        if identity and Upload.objects.filter(identity=identity, state__in=ACTIVE).exists():
            raise IntakeError("processing_in_progress")
        user.delete()


STORAGE_ERRORS = (BotoCoreError, ClientError, OSError, TimeoutError)
