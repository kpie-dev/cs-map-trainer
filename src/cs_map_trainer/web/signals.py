from django.contrib.auth import get_user_model
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import PracticeReview, Upload


@receiver(pre_delete, sender=get_user_model())
def erase_user_results(sender, instance, **kwargs):
    from .billing import close_account

    close_account(instance)
    # Lock uploads first so a concurrent review cannot survive account deletion.
    Upload.objects.filter(owner=instance).update(
        report=None,
        scripts=None,
        selection=None,
        state=Upload.State.DELETED,
        cleanup_pending=True,
    )
    PracticeReview.objects.filter(upload__owner=instance).delete()
