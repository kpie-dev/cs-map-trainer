from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from cs_map_trainer.analysis import BASE_LIMITATIONS
from cs_map_trainer.callouts import format_place_name
from cs_map_trainer.exporting import ASSUMPTIONS, SESSION_CHANGES, ExportError, export_scenario
from cs_map_trainer.maps import map_label

from . import billing
from .identity import verified_email
from .models import BillingAccount, PracticeReview, Upload
from .practice import practice_queue, review_scenario
from .presentation import LIMITATIONS, STATES, error_message
from .services import (
    ACTIVE,
    IntakeError,
    delete_account,
    delete_history,
    get_training_selection,
    save_training_selection,
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
    return render(
        request,
        "trainer/account.html",
        {"billing": BillingAccount.objects.filter(owner=request.user).first()},
    )


@require_POST
@private_page
def billing_checkout(request):
    return redirect(billing.checkout(request.user))


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
        .annotate(report_map_name=KeyTextTransform("name", KeyTextTransform("map", "report")))
        .order_by("-created_at", "-id")
    )
    page = Paginator(uploads, 20).get_page(request.GET.get("page"))
    for upload in page:
        upload.state_label = STATES[upload.state]
        upload.map_label = map_label(
            upload.report_map_name if upload.state == Upload.State.READY else None
        )
    return render(request, "trainer/history.html", {"page": page})


@require_GET
@private_page
def report(request, upload_id):
    upload = Upload.objects.exclude(state=Upload.State.DELETED).get(
        pk=upload_id, owner=request.user
    )
    context = {
        "upload": upload,
        "state_label": STATES[upload.state],
        "active": upload.state in ACTIVE,
        "failure": error_message(upload.error_code) if upload.error_code else None,
        "map_label": map_label(None),
    }
    if upload.state == Upload.State.READY:
        analysis = validated_report(upload)
        context["analysis"] = analysis
        context["map_label"] = map_label(analysis.map.name)
        context["limitations"] = list(analysis.limitations)
        if analysis.scenario_document is not None:
            selection = get_training_selection(request.user, upload.pk)
            context["situations"] = []
            for item in analysis.scenario_document.scenarios:
                locations = analysis.scenario_locations.get(item.scenario_id)
                context["situations"].append(
                    {
                        "scenario": item,
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
    return render(request, "trainer/report.html", context)


@require_POST
@private_page
def selection(request, upload_id):
    _, document = training_result(request.user, upload_id)
    include, reject = [], []
    for item in document.scenarios:
        choices = request.POST.getlist(f"choice_{item.scenario_id}")
        if len(choices) != 1 or choices[0] not in {"include", "reject", "omit"}:
            raise IntakeError("invalid_selection_payload", 400)
        if choices[0] == "include":
            include.append(item.scenario_id)
        elif choices[0] == "reject":
            reject.append(item.scenario_id)
    save_training_selection(request.user, upload_id, {"include": include, "reject": reject})
    messages.success(request, "Your scenario selection has been saved.")
    return redirect("report", upload_id=upload_id)


@require_GET
@private_page
def training(request, upload_id):
    upload, document = training_result(request.user, upload_id)
    selection = get_training_selection(request.user, upload_id)
    scenarios = [
        item
        for item in document.scenarios
        if item.scenario_id in selection["selected_scenario_ids"]
    ]
    scenario_id = request.GET.get("scenario", scenarios[0].scenario_id)
    current = next((item for item in scenarios if item.scenario_id == scenario_id), None)
    if current is None:
        raise IntakeError("scenario_not_found", 404)
    index = scenarios.index(current)
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
            "previous": scenarios[index - 1] if index else None,
            "following": scenarios[index + 1] if index + 1 < len(scenarios) else None,
            "exported": exported,
            "export_error": export_error,
            "limitations": [LIMITATIONS.get(code, code) for code in current.limitations],
            "review": upload.practice_reviews.filter(scenario_id=scenario_id).first(),
            "ratings": PracticeReview.Rating.choices,
            "assumptions": ASSUMPTIONS,
            "session_changes": SESSION_CHANGES,
        },
    )


@require_POST
@private_page
def review(request, upload_id, scenario_id):
    ratings = request.POST.getlist("rating")
    review_scenario(request.user, upload_id, scenario_id, ratings[0] if len(ratings) == 1 else None)
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
    category = request.GET.get("filter", "due")
    entries = practice_queue(request.user, category)
    return render(
        request,
        "trainer/practice.html",
        {"page": Paginator(entries, 20).get_page(request.GET.get("page")), "category": category},
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
