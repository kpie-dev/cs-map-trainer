import json
import logging
import re
import uuid
from functools import wraps

from allauth.socialaccount.providers.steam.views import SteamOpenIDCallbackView, steam_login
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from cs_map_trainer.exporting import ASSUMPTIONS, COMPATIBILITY, EXPORTER_VERSION, SESSION_CHANGES

from .identity import verified_email
from .models import SteamIdentity, Upload
from .presentation import error_message
from .services import (
    STORAGE_ERRORS,
    IntakeError,
    complete,
    delete_account,
    delete_history,
    get_training_selection,
    initiate,
    save_training_selection,
    training_export,
    training_pack,
)
from .storage import R2

logger = logging.getLogger(__name__)


class PrivateSteamCallbackView(SteamOpenIDCallbackView):
    def complete_login(self, login):
        # allauth's lookup can persist extra_data before pre_social_login runs.
        login.account.extra_data = {"steamid": login.account.uid}
        return super().complete_login(login)


steam_callback = PrivateSteamCallbackView.as_view()


def operation_error(request, code, status):
    if "text/html" in request.headers.get("Accept", ""):
        return render(
            request,
            "trainer/error.html",
            {"error": error_message(code), "error_code": code},
            status=status,
        )
    return JsonResponse({"error": code}, status=status)


def private(view):
    @wraps(view)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not verified_email(request.user):
            return operation_error(request, "verified_email_required", 403)
        try:
            return view(request, *args, **kwargs)
        except IntakeError as error:
            return operation_error(request, error.code, error.status)
        except Upload.DoesNotExist:
            return operation_error(request, "not_found", 404)
        except ImproperlyConfigured:
            logger.exception("Storage configuration missing for authenticated backend operation")
            return operation_error(request, "storage_not_configured", 503)
        except STORAGE_ERRORS:
            logger.exception("Storage request failed for authenticated backend operation")
            return operation_error(request, "storage_unavailable", 503)

    return wrapped


def body(request):
    try:
        result = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as error:
        raise IntakeError("invalid_json", 400) from error
    if not isinstance(result, dict):
        raise IntakeError("invalid_json_object", 400)
    return result


def serialize(upload, *, include_result=False):
    result = {
        "id": str(upload.pk),
        "state": upload.state,
        "created_at": upload.created_at.isoformat(),
        "error": upload.error_code or None,
        "cleanup_pending": upload.cleanup_pending,
        "cleanup_error": upload.cleanup_error or None,
        "compatibility": "unverified_in_game",
    }
    if include_result:
        result.update(report=upload.report, scripts=upload.scripts, selection=upload.selection)
    return result


@require_GET
@ensure_csrf_cookie
@private
def history(request):
    return JsonResponse(
        {
            "steam_linked": SteamIdentity.objects.filter(owner=request.user).exists(),
            "uploads": [
                serialize(upload)
                for upload in Upload.objects.filter(owner=request.user)
                .exclude(state=Upload.State.DELETED)
                .defer("report", "scripts", "selection")
                .order_by("-created_at")[:100]
            ],
        }
    )


@require_POST
@private
def upload_start(request):
    data = body(request)
    if data.get("has_upload_rights") is not True:
        raise IntakeError("upload_rights_confirmation_required", 400)
    try:
        request_id = uuid.UUID(data["request_id"])
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise IntakeError("invalid_request_id", 400) from error
    storage = R2()
    upload = initiate(request.user, request_id, data.get("size_bytes"), storage)
    response = serialize(upload)
    if upload.state == Upload.State.UPLOADING and upload.expires_at > timezone.now():
        response.update(
            upload_url=storage.sign(upload),
            method="PUT",
            size_bytes=upload.size_bytes,
            instructions="Send the raw File/Blob as the body; not a multipart/form-data form.",
        )
    return JsonResponse(response, status=201)


@require_POST
@private
def upload_complete(request, upload_id):
    return JsonResponse(serialize(complete(request.user, upload_id)))


@require_http_methods(["GET", "DELETE"])
@private
def upload_detail(request, upload_id):
    if request.method == "DELETE":
        delete_history(request.user, upload_id)
        return JsonResponse({"deleted": True})
    upload = Upload.objects.exclude(state=Upload.State.DELETED).get(
        pk=upload_id, owner=request.user
    )
    return JsonResponse(serialize(upload, include_result=True))


@require_http_methods(["GET", "POST"])
@private
def upload_selection(request, upload_id):
    if request.method == "POST":
        result = save_training_selection(request.user, upload_id, body(request))
    else:
        result = get_training_selection(request.user, upload_id)
    return JsonResponse(result)


@require_GET
@private
def upload_pack(request, upload_id):
    if set(request.GET) - {"include_cfg"} or request.GET.getlist("include_cfg") not in (
        [],
        ["true"],
        ["false"],
    ):
        raise IntakeError("invalid_export_parameters", 400)
    pack = training_pack(
        request.user, upload_id, include_cfg=request.GET.get("include_cfg") == "true"
    )
    response = HttpResponse(pack.archive, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="training-{upload_id}.zip"'
    return response


@require_GET
@private
def upload_export(request, upload_id, scenario_id):
    if set(request.GET) - {"format"} or request.GET.getlist("format") not in (
        [],
        ["json"],
        ["cfg"],
    ):
        raise IntakeError("invalid_export_parameters", 400)
    scenario, exported = training_export(request.user, upload_id, scenario_id)
    if request.GET.get("format") == "cfg":
        response = HttpResponse(exported.cfg, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="scenario.cfg"'
        return response
    return JsonResponse(
        {
            "scenario_id": scenario.scenario_id,
            "console_line": exported.console_line,
            "exporter_version": EXPORTER_VERSION,
            "compatibility": COMPATIBILITY,
            "map": scenario.map.model_dump(),
            "source": scenario.source.model_dump(),
            "limitations": scenario.limitations,
            "assumptions": list(ASSUMPTIONS),
            "session_changes": list(SESSION_CHANGES),
        }
    )


@require_POST
@private
def account_delete(request):
    if not request.user.check_password(body(request).get("password", "")):
        raise IntakeError("password_confirmation_required", 403)
    delete_account(request.user)
    logout(request)
    return JsonResponse({"deleted": True})


@require_POST
@private
def connect_steam(request):
    if request.POST.get("process") != "connect":
        raise IntakeError("steam_connect_process_required", 400)
    if not settings.SOCIALACCOUNT_PROVIDERS["steam"]["APP"]["secret"]:
        raise IntakeError("steam_not_configured", 503)
    return steam_login(request)


@require_GET
@private
@transaction.atomic
def connected_steam(request):
    if request.GET.get("openid.op_endpoint") != "https://steamcommunity.com/openid/login":
        raise IntakeError("invalid_steam_endpoint", 400)
    claimed = request.GET.get("openid.claimed_id", "")
    if (
        not re.fullmatch(r"https://steamcommunity\.com/openid/id/[0-9]{17}", claimed)
        or request.GET.get("openid.identity") != claimed
    ):
        raise IntakeError("invalid_steam_identity", 400)
    return steam_callback(request)
