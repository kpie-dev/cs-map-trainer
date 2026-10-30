from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models.fields.json import KeyTextTransform
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from cs_map_trainer.analysis import BASE_LIMITATIONS
from cs_map_trainer.callouts import format_place_name
from cs_map_trainer.exporting import ASSUMPTIONS, SESSION_CHANGES, ExportError, export_scenario
from cs_map_trainer.maps import map_label
from cs_map_trainer.training_groups import expand_group_selection

from . import billing
from .grouping import present_groups
from .identity import verified_email
from .models import BillingAccount, Upload
from .practice import practice_library, review_scenario
from .presentation import LIMITATIONS, STATES, error_message
from .services import (
    ACTIVE,
    IntakeError,
    attach_player,
    delete_account,
    delete_history,
    get_training_selection,
    save_training_selection,
    submit_training_selection,
    training_result,
    validated_report,
)


def private_page(view):
    @wraps(view)
    @never_cache
    @login_required
    def wrapped(request, *args, **kwargs):
        if not verified_email(request.user):
            return redirect("account_email")
        try:
            return view(request, *args, **kwargs)
        except Upload.DoesNotExist:
            return render(
                request,
                "trainer/error.html",
                {"error": error_message("not_found"), "error_code": "not_found"},
                status=404,
            )
        except IntakeError as error:
            return render(
                request,
                "trainer/error.html",
                {"error": error_message(error.code), "error_code": error.code},
                status=error.status,
            )

    return wrapped


@require_GET
@never_cache
def home(request):
    return render(request, "trainer/home.html")


@require_GET
@never_cache
@login_required
def account(request):
    from .teams import roster_members

    members = list(roster_members(request.user))
    return render(
        request,
        "trainer/account.html",
        {
            "billing": BillingAccount.objects.filter(owner=request.user).first(),
            "team_members": members,
            "roster_slots": [
                members[index] if index < len(members) else None for index in range(5)
            ],
        },
    )


@require_POST
@private_page
def billing_checkout(request):
    return redirect(billing.checkout(request.user, request.POST.get("plan", "pro")))


@require_POST
@private_page
def billing_change(request):
    billing.schedule_plan(request.user, request.POST.get("plan"))
    messages.success(request, "Plan change scheduled for your next renewal.")
    return redirect("account")


@require_POST
@private_page
def team_save(request):
    from .teams import save_roster

    ids, names = request.POST.getlist("steam_id"), request.POST.getlist("name")
    if len(ids) != 5 or len(names) != 5:
        raise IntakeError("invalid_team_roster", 400)
    if any(
        not steam_id.strip() and name.strip() for steam_id, name in zip(ids, names, strict=True)
    ):
        raise IntakeError("invalid_team_roster", 400)
    save_roster(
        request.user,
        [
            {"steam_id": steam_id, "name": name}
            for steam_id, name in zip(ids, names, strict=True)
            if steam_id.strip()
        ],
    )
    messages.success(request, "Team roster saved. Existing analyses are unchanged.")
    return redirect("account")


@require_POST
@private_page
def billing_portal(request):
    return redirect(billing.portal(request.user))


@require_POST
@private_page
def billing_refresh(request):
    billing.reconcile_user(request.user)
    messages.success(request, "Subscription status updated from Stripe.")
    return redirect("account")


@require_GET
@private_page
def billing_return(request):
    messages.info(
        request,
        "Returning from Stripe does not confirm payment. Check your subscription status "
        "or select Refresh payment status.",
    )
    return redirect("account")


@require_GET
@private_page
def history(request):
    uploads = (
        Upload.objects.filter(owner=request.user)
        .exclude(state=Upload.State.DELETED)
        .defer("report", "scripts", "selection")
        .prefetch_related("player_results")
        .annotate(report_map_name=KeyTextTransform("name", KeyTextTransform("map", "report")))
        .order_by("-created_at", "-id")
    )
    page = Paginator(uploads, 20).get_page(request.GET.get("page"))
    for upload in page:
        upload.state_label = STATES[upload.state]
        upload.map_label = map_label(
            upload.report_map_name if upload.state == Upload.State.READY else None
        )
        results = list(upload.player_results.all())
        if results and results[0].report:
            upload.map_label = map_label(results[0].report["map"]["name"])
        upload.player_labels = ", ".join(result.name or result.steam_id for result in results)
    return render(request, "trainer/history.html", {"page": page})


@require_GET
@private_page
def report(request, upload_id, steam_id=None):
    return render_report(request, upload_id, steam_id=steam_id)


def player_urls(upload, steam_id):
    prefix = f"/uploads/{upload.pk}/"
    backend = f"/backend/uploads/{upload.pk}/"
    if steam_id:
        prefix += f"players/{steam_id}/"
        backend += f"players/{steam_id}/"
    return {
        "report_url": prefix,
        "selection_url": prefix + "selection/",
        "training_url": prefix + "training/",
        "backend_url": backend,
    }


def render_report(request, upload_id, *, submitted=None, error=None, steam_id=None):
    upload = Upload.objects.exclude(state=Upload.State.DELETED).get(
        pk=upload_id, owner=request.user
    )
    context = {
        "upload": upload,
        "state_label": STATES[upload.state],
        "active": upload.state in ACTIVE,
        "failure": error_message(upload.error_code) if upload.error_code else None,
        "map_label": map_label(None),
        "selection_error": error_message(error.code) if error else None,
        **player_urls(upload, steam_id),
    }
    if upload.mode == "team":
        context["players"] = list(upload.player_results.all())
        if steam_id is None:
            return render(request, "trainer/team_report.html", context)
        context["team_upload"] = True
    attach_player(upload, steam_id)
    context["player_result"] = upload.analysis_result
    if upload.state == Upload.State.READY:
        analysis = validated_report(upload)
        context["analysis"] = analysis
        context["map_label"] = map_label(analysis.map.name)
        context["limitations"] = list(analysis.limitations)
        if analysis.scenario_document is not None:
            selection = get_training_selection(request.user, upload.pk, steam_id=steam_id)
            context["situations"] = []
            for item in analysis.scenario_document.scenarios:
                locations = analysis.scenario_locations.get(item.scenario_id)
                context["situations"].append(
                    {
                        "scenario": item,
                        "export_failed": error and item.scenario_id in error.scenario_ids,
                        "locations": locations,
                        "victim_location": format_place_name(item.map.name, locations.player)
                        if locations
                        else None,
                        "killer_location": format_place_name(item.map.name, locations.opponent)
                        if locations
                        else None,
                        "warnings": [
                            code for code in item.limitations if code not in BASE_LIMITATIONS
                        ],
                        "choice": (
                            "include"
                            if item.scenario_id in selection["selected_scenario_ids"]
                            else "reject"
                            if item.scenario_id in selection["reject"]
                            else "omit"
                        ),
                    }
                )
            context["locations_not_recorded"] = any(
                item["locations"] is None for item in context["situations"]
            )
            for item in analysis.scenario_document.scenarios:
                for code in item.limitations:
                    if code in BASE_LIMITATIONS and code not in context["limitations"]:
                        context["limitations"].append(code)
            context["selected_count"] = len(selection["selected_scenario_ids"])
            if submitted is not None:
                for item in context["situations"]:
                    item["choice"] = (
                        "include" if item["scenario"].scenario_id in submitted else "omit"
                    )
                context["selected_count"] = len(submitted)
            context["training_groups"] = present_groups(
                analysis,
                submitted if submitted is not None else selection["selected_scenario_ids"],
            )
            context["selected_group_count"] = sum(
                bool(group["selected"]) for group in context["training_groups"]
            )
            for group in context["training_groups"]:
                group["export_failed"] = bool(
                    error
                    and any(
                        member["scenario"].scenario_id in error.scenario_ids
                        for member in group["members"]
                    )
                )
    return render(request, "trainer/report.html", context, status=error.status if error else 200)


@require_POST
@private_page
def selection(request, upload_id, steam_id=None):
    if request.POST.get("selection_ui") in {"checkboxes", "groups"}:
        grouped = request.POST.get("selection_ui") == "groups"
        included = request.POST.getlist("group" if grouped else "include")
        partial = None
        intent = request.POST.get("intent")
        try:
            if grouped:
                partial = {}
                for key in request.POST:
                    if key.startswith("partial_"):
                        values = request.POST.getlist(key)
                        if len(values) != 1:
                            raise IntakeError("invalid_selection_payload", 400)
                        gid = key.removeprefix("partial_")
                        partial[gid] = {
                            "action": values[0],
                            "members": request.POST.getlist(f"members_{gid}"),
                        }
                if {
                    key.removeprefix("members_")
                    for key in request.POST
                    if key.startswith("members_")
                } != set(partial):
                    raise IntakeError("invalid_selection_payload", 400)
            if intent not in {"download", "practice"}:
                raise IntakeError("invalid_selection_payload", 400)
            pack = submit_training_selection(
                request.user,
                upload_id,
                included,
                download=intent == "download",
                partial=partial,
                steam_id=steam_id,
            )
        except IntakeError as error:
            if request.headers.get("Accept") == "application/json":
                return JsonResponse(
                    {"error": error.code, "scenario_ids": error.scenario_ids}, status=error.status
                )
            submitted = included
            if grouped:
                try:
                    _, document = training_result(request.user, upload_id, steam_id=steam_id)
                    submitted = expand_group_selection(document, included, partial or {})
                except (ValueError, TypeError, IntakeError):
                    submitted = None
            return render_report(
                request, upload_id, submitted=submitted, error=error, steam_id=steam_id
            )
        if pack is not None:
            response = HttpResponse(pack.archive, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="training-{upload_id}.zip"'
            return response
        return redirect(player_urls_by_id(upload_id, steam_id, "training"))
    _, document = training_result(request.user, upload_id, steam_id=steam_id)
    include, reject = [], []
    for item in document.scenarios:
        choices = request.POST.getlist(f"choice_{item.scenario_id}")
        if len(choices) != 1 or choices[0] not in {"include", "reject", "omit"}:
            raise IntakeError("invalid_selection_payload", 400)
        if choices[0] == "include":
            include.append(item.scenario_id)
        elif choices[0] == "reject":
            reject.append(item.scenario_id)
    save_training_selection(
        request.user, upload_id, {"include": include, "reject": reject}, steam_id=steam_id
    )
    messages.success(request, "Your scenario selection has been saved.")
    return redirect(player_urls_by_id(upload_id, steam_id, "report"))


def player_urls_by_id(upload_id, steam_id, action):
    if steam_id:
        return reverse(f"player_{action}", kwargs={"upload_id": upload_id, "steam_id": steam_id})
    return reverse(action, kwargs={"upload_id": upload_id})


@require_GET
@private_page
def training(request, upload_id, steam_id=None):
    upload, document = training_result(request.user, upload_id, steam_id=steam_id)
    selection = get_training_selection(request.user, upload_id, steam_id=steam_id)
    scenarios = [
        item
        for item in document.scenarios
        if item.scenario_id in selection["selected_scenario_ids"]
    ]
    analysis = validated_report(upload)
    groups = [
        group
        for group in present_groups(analysis, selection["selected_scenario_ids"])
        if group["selected"]
    ]
    scenario_id = request.GET.get("scenario", groups[0]["first"]["scenario"].scenario_id)
    current = next((item for item in scenarios if item.scenario_id == scenario_id), None)
    if current is None:
        raise IntakeError("scenario_not_found", 404)
    current_group = next(
        group
        for group in groups
        if any(member["scenario"] == current for member in group["selected"])
    )
    index = groups.index(current_group)
    members = [member["scenario"] for member in current_group["selected"]]
    member_index = members.index(current)
    locations = analysis.scenario_locations.get(current.scenario_id)
    exported, export_error = None, None
    try:
        exported = export_scenario(current)
    except ExportError:
        export_error = error_message("scenario_not_exportable")
    return render(
        request,
        "trainer/training.html",
        {
            "upload": upload,
            "scenarios": scenarios,
            "current": current,
            "map_label": map_label(current.map.name),
            "position": index + 1,
            "training_groups": groups,
            "current_group": current_group,
            "member_position": member_index + 1,
            "current_member": next(
                member for member in current_group["selected"] if member["scenario"] == current
            ),
            "previous": groups[index - 1]["first"]["scenario"] if index else None,
            "following": groups[index + 1]["first"]["scenario"]
            if index + 1 < len(groups)
            else None,
            "exported": exported,
            "export_error": export_error,
            "limitations": [LIMITATIONS.get(code, code) for code in current.limitations],
            "warnings": [code for code in current.limitations if code not in BASE_LIMITATIONS],
            "player_location": format_place_name(current.map.name, locations.player)
            if locations
            else None,
            "opponent_location": format_place_name(current.map.name, locations.opponent)
            if locations
            else None,
            "locations_recorded": locations is not None,
            "assumptions": ASSUMPTIONS,
            "session_changes": SESSION_CHANGES,
            "player_result": upload.analysis_result,
            **player_urls(upload, steam_id),
        },
    )


@require_POST
@private_page
def review(request, upload_id, scenario_id, steam_id=None):
    ratings = request.POST.getlist("rating")
    review_scenario(
        request.user,
        upload_id,
        scenario_id,
        ratings[0] if len(ratings) == 1 else None,
        steam_id=steam_id,
    )
    messages.success(
        request,
        "Practice rating cleared. Scenario restored to your queue."
        if ratings == ["restore"]
        else "Practice rating saved. This is your feedback, not an in-game result.",
    )
    return redirect("practice")


@require_GET
@private_page
def practice(request):
    entries = practice_library(request.user)
    players = {}
    for entry in entries:
        players.setdefault(entry["steam_id"], entry["player_name"] or entry["steam_id"])
    selected_player = request.GET.get("player")
    if selected_player is not None and selected_player not in players:
        raise IntakeError("player_not_found", 404)
    if selected_player:
        entries = [entry for entry in entries if entry["steam_id"] == selected_player]
    elif any(entry["team"] for entry in entries):
        entries = []
    return render(
        request,
        "trainer/practice.html",
        {
            "page": Paginator(entries, 20).get_page(request.GET.get("page")),
            "players": players.items(),
            "selected_player": selected_player,
            "choose_player": not selected_player and bool(players) and not entries,
        },
    )


@require_POST
@private_page
def remove_upload(request, upload_id):
    if request.POST.get("confirm") != "yes":
        raise IntakeError("delete_confirmation_required", 400)
    delete_history(request.user, upload_id)
    messages.success(request, "Report, scenario selection and practice ratings deleted.")
    return redirect("history")


@require_POST
@private_page
def remove_account(request):
    if request.POST.get("confirm") != "yes":
        raise IntakeError("delete_confirmation_required", 400)
    if not request.user.check_password(request.POST.get("password", "")):
        raise IntakeError("password_confirmation_required", 403)
    delete_account(request.user)
    logout(request)
    return redirect("home")
