import re

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.db import IntegrityError, transaction
from django.http import JsonResponse

from .models import SteamIdentity


def verified_email(user):
    return user.is_authenticated and EmailAddress.objects.filter(user=user, verified=True).exists()


class SteamAdapter(DefaultSocialAccountAdapter):
    def list_providers(self, request):
        return [provider for provider in super().list_providers(request) if provider.id == "steam"]

    def pre_social_login(self, request, sociallogin):
        account = sociallogin.account
        if (
            account.provider != "steam"
            or sociallogin.state.get("process") != "connect"
            or not verified_email(request.user)
            or not re.fullmatch(r"[0-9]{17}", account.uid)
        ):
            raise ImmediateHttpResponse(
                JsonResponse({"error": "steam_connection_required"}, status=403)
            )
        try:
            with transaction.atomic():
                identity, _ = SteamIdentity.objects.get_or_create(
                    steam_id=account.uid, defaults={"owner": request.user}
                )
                if identity.owner_id != request.user.pk:
                    raise ImmediateHttpResponse(
                        JsonResponse({"error": "steam_already_linked"}, status=409)
                    )
        except IntegrityError as error:
            raise ImmediateHttpResponse(
                JsonResponse({"error": "steam_link_conflict"}, status=409)
            ) from error

    def validate_disconnect(self, account, accounts):
        from django.core.exceptions import ValidationError

        raise ValidationError("Steam linking is permanent; contact support for recovery.")

    def is_open_for_signup(self, request, sociallogin):
        return False
