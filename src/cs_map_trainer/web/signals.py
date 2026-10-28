from django.contrib.auth import get_user_model
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Upload


@receiver(pre_delete, sender=get_user_model())
def erase_user_results(sender, instance, **kwargs):
    Upload.objects.filter(owner=instance).update(
        report=None,
        scripts=None,
        state=Upload.State.DELETED,
        cleanup_pending=True,
    )
