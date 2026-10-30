from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model


def verified_email(user):
    return user.is_authenticated and EmailAddress.objects.filter(user=user, verified=True).exists()


def lock_account(user):
    return get_user_model().objects.select_for_update().get(pk=user.pk)
