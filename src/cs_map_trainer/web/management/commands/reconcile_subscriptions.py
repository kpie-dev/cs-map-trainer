from django.core.management.base import BaseCommand, CommandError

from cs_map_trainer.web.billing import reconcile_account
from cs_map_trainer.web.models import BillingAccount
from cs_map_trainer.web.services import IntakeError


class Command(BaseCommand):
    help = "Reconcile Stripe subscriptions after missing or delayed webhooks."

    def handle(self, *args, **options):
        failures = 0
        accounts = BillingAccount.objects.filter(customer_id__isnull=False)
        for account in accounts.iterator(chunk_size=50):
            try:
                reconcile_account(account.pk)
            except IntakeError as error:
                failures += 1
                self.stderr.write(f"Billing account {account.pk}: {error.code}")
        if failures:
            raise CommandError(f"Could not reconcile {failures} billing accounts")
        self.stdout.write("Stripe subscriptions reconciled.")
