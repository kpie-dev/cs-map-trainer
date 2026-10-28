import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta

import psutil
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from cs_map_trainer.analysis import AnalysisReport
from cs_map_trainer.exporting import ExportError, export_scenario

from .models import SteamIdentity, Upload
from .processes import parser_slot
from .services import STORAGE_ERRORS, TERMINAL, dispatch
from .storage import R2, InvalidUpload

logger = logging.getLogger(__name__)
WORKER_LOCK = 184731901


class DemoRejected(ValueError):
    pass


def run_parser(upload, directory, *, lock_fd=None):
    output = directory / "result.json"
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG") if key in os.environ}
    env.update(
        PARSER_MEMORY_BYTES=str(settings.PARSER_MEMORY_BYTES),
        PARSER_TIMEOUT_SECONDS=str(settings.PARSER_TIMEOUT_SECONDS),
        POLARS_MAX_THREADS="2",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        PARSER_PARENT_PID=str(os.getpid()),
    )
    run_bounded(
        [
            sys.executable,
            "-m",
            "cs_map_trainer.web.processor",
            str(directory / "input.dem"),
            upload.identity_id,
            str(output),
        ],
        env,
        lock_fd=lock_fd,
    )
    if output.stat().st_size > 16 * 1024**2:
        raise ValueError("Parser output exceeds its budget")
    result = json.loads(output.read_text())
    if result.get("error"):
        if result["error"] == "linked_player_not_in_demo":
            raise DemoRejected(result["error"])
        if result["error"] != "unsupported_or_invalid_demo":
            raise ValueError("Invalid parser error")
        return None, None
    report = AnalysisReport.model_validate(result["report"])
    if report.player_steam_id != upload.identity_id:
        raise ValueError("Parser returned a different player")
    # Derive commands from the validated report, never trust commands from a child payload.
    scripts = []
    if report.scenario_document:
        for scenario in report.scenario_document.scenarios:
            try:
                scripts.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "console_line": export_scenario(scenario).console_line,
                        "error": None,
                    }
                )
            except ExportError:
                scripts.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "console_line": None,
                        "error": "scenario_not_exportable",
                    }
                )
    return report.model_dump(mode="json"), scripts


def run_bounded(command, env, *, lock_fd=None):
    started = time.monotonic()
    with subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=() if lock_fd is None else (lock_fd,),
    ) as process:
        try:
            monitor = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    if monitor.memory_info().rss > settings.PARSER_MEMORY_BYTES:
                        raise MemoryError("Parser exceeded its RSS budget")
                except psutil.NoSuchProcess:
                    break
                if time.monotonic() - started > settings.PARSER_TIMEOUT_SECONDS:
                    raise subprocess.TimeoutExpired(command, settings.PARSER_TIMEOUT_SECONDS)
                time.sleep(0.05)
            code = process.wait()
            if code:
                raise subprocess.CalledProcessError(code, command)
        except BaseException:
            process.kill()
            process.wait()
            raise


def cleanup(upload, storage=None):
    directory = settings.WORK_ROOT / str(upload.pk)
    try:
        if directory.exists():
            shutil.rmtree(directory)
        (storage or R2()).delete(upload)
    except (*STORAGE_ERRORS, ValueError):
        logger.exception("Input cleanup failed for upload %s", upload.pk)
        Upload.objects.filter(pk=upload.pk).update(
            cleanup_pending=True, cleanup_error="input_cleanup_failed"
        )
        return False
    Upload.objects.filter(pk=upload.pk).update(
        cleanup_pending=False, cleanup_error="", input_deleted_at=timezone.now()
    )
    return True


def process_upload(upload_id):
    with parser_slot(settings.WORK_ROOT) as lock:
        if lock is None:
            logger.warning("Parser slot busy; upload %s remains in the outbox", upload_id)
            return
        _process_upload(upload_id, lock.fileno())


def _process_upload(upload_id, lock_fd):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [WORKER_LOCK])
        acquired = cursor.fetchone()[0]
    if not acquired:
        logger.warning("Worker busy; queued upload %s remains in the outbox", upload_id)
        return
    try:
        with transaction.atomic():
            upload = Upload.objects.select_for_update().get(pk=upload_id)
            if upload.state != Upload.State.QUEUED or upload.owner_id is None:
                return
            upload.state = Upload.State.RUNNING
            upload.started_at = timezone.now()
            upload.save(update_fields=["state", "started_at"])
        state, error, charged = Upload.State.FAILED, "processing_failed", False
        report, scripts = None, None
        try:
            directory = settings.WORK_ROOT / str(upload.pk)
            directory.mkdir(parents=True, mode=0o700, exist_ok=False)
            storage = R2()
            storage.download(upload, directory / "input.dem")
            report, scripts = run_parser(upload, directory, lock_fd=lock_fd)
            if report is None:
                state, error, charged = (
                    Upload.State.UNSUPPORTED,
                    "unsupported_or_invalid_demo",
                    True,
                )
            else:
                state, error, charged = Upload.State.READY, "", True
        except DemoRejected as rejection:
            state, error, charged = Upload.State.UNSUPPORTED, str(rejection), True
            logger.warning("Linked player absent from upload %s", upload.pk)
        except InvalidUpload:
            state, error, charged = Upload.State.UNSUPPORTED, "invalid_demo_object", True
            logger.warning("Invalid stored demo for upload %s", upload.pk)
        except Exception as failure:
            # The task boundary must persist infrastructure/native-parser failures and clean input.
            logger.error("Processing failed for upload %s (%s)", upload.pk, type(failure).__name__)
        finally:
            try:
                Upload.objects.filter(
                    pk=upload.pk, state=Upload.State.RUNNING, owner__isnull=False
                ).update(
                    state=state,
                    error_code=error,
                    quota_charged=charged,
                    report=report,
                    scripts=scripts,
                    finished_at=timezone.now(),
                )
            finally:
                cleanup(upload)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [WORKER_LOCK])


def maintain():
    now = timezone.now()
    expired = Upload.objects.filter(state=Upload.State.UPLOADING, expires_at__lte=now)
    expired.update(
        state=Upload.State.EXPIRED,
        quota_charged=False,
        error_code="upload_expired",
        finished_at=now,
    )
    stale = Upload.objects.filter(
        state=Upload.State.RUNNING,
        started_at__lte=now - timedelta(seconds=settings.JOB_LEASE_SECONDS),
    )
    stale.update(
        state=Upload.State.FAILED,
        quota_charged=False,
        error_code="worker_lost",
        finished_at=now,
    )
    Upload.objects.filter(state=Upload.State.QUEUED, expires_at__lte=now).update(
        state=Upload.State.EXPIRED,
        quota_charged=False,
        error_code="queue_expired",
        finished_at=now,
    )
    for upload in (
        Upload.objects.filter(state__in=TERMINAL, cleanup_pending=True)
        .defer("report", "scripts")
        .iterator(chunk_size=50)
    ):
        cleanup(upload)
    for upload in (
        Upload.objects.filter(state=Upload.State.QUEUED)
        .filter(dispatched_at__isnull=True)
        .iterator()
    ):
        dispatch(upload.pk)
    for upload in Upload.objects.filter(
        state=Upload.State.QUEUED,
        dispatched_at__lt=now - timedelta(seconds=settings.Q_CLUSTER["retry"]),
    ).iterator():
        dispatch(upload.pk)
    Upload.objects.filter(state__in=TERMINAL, cleanup_pending=False).annotate(
        quota_at=Coalesce("accepted_at", "created_at")
    ).filter(quota_at__lt=now - timedelta(days=7)).filter(
        Q(owner__isnull=True) | Q(state=Upload.State.DELETED)
    ).delete()
    SteamIdentity.objects.filter(owner__isnull=True, upload__isnull=True).delete()
    clean_orphans(now)


def clean_orphans(now):
    storage = R2()
    cutoff = now - timedelta(seconds=settings.UPLOAD_EXPIRE_SECONDS)
    for item in storage.orphans(cutoff):
        if not Upload.objects.filter(key=item["key"]).exists():
            storage.delete_orphan(item)
    if settings.WORK_ROOT.exists():
        for directory in settings.WORK_ROOT.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                from uuid import UUID

                upload_id = UUID(directory.name)
            except ValueError:
                logger.error("Unexpected entry in worker scratch directory: %s", directory.name)
                continue
            if not Upload.objects.filter(pk=upload_id, state=Upload.State.RUNNING).exists():
                shutil.rmtree(directory)
