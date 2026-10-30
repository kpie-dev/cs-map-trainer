from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .billing import process_event, verify_signature
from .services import IntakeError


@csrf_exempt
@require_POST
@never_cache
def stripe_webhook(request):
    raw = request.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        return JsonResponse({"error": "billing_webhook_too_large"}, status=413)
    try:
        event = verify_signature(raw, request.headers.get("Stripe-Signature", ""))
        process_event(event)
    except IntakeError as error:
        return JsonResponse({"error": error.code}, status=error.status)
    return JsonResponse({"received": True})
