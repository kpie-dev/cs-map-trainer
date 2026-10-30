from django.core.management.base import BaseCommand, CommandError

from cs_map_trainer.web.billing import migrate_legacy_price
from cs_map_trainer.web.models import BillingAccount
from cs_map_trainer.web.services import IntakeError


class Command(BaseCommand):
    help = (
        "Schedule legacy $7.99 Pro subscriptions to $4.99 at renewal. "
        "Defaults to dry-run; pass --apply to modify Stripe. "
        "Existing future plan changes and cancellations are never overwritten; "
        "interrupted application-owned schedules can be recovered."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Read only (the default).")
        mode.add_argument("--apply", action="store_true", help="Create renewal schedules.")

    def handle(self, *args, **options):
        failures = 0
        accounts = BillingAccount.objects.filter(closed=False, owner__isnull=False).exclude(
            customer_id__isnull=True
        )
        for account in accounts.iterator(chunk_size=50):
            try:
                result = migrate_legacy_price(account.pk, dry_run=not options["apply"])
                self.stdout.write(f"Billing account {account.pk}: {result}")
            except IntakeError as error:
                failures += 1
                self.stderr.write(f"Billing account {account.pk}: {error.code}")
        if failures:
            raise CommandError(f"Could not migrate {failures} billing accounts")
