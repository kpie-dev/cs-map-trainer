from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Synchronize minimal support groups; optionally assign or remove support access."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Explicitly assign a role to an existing account.")
        parser.add_argument("--role", choices=["Support", "Account Operators"])
        parser.add_argument(
            "--remove", action="store_true", help="Remove support roles and staff access."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email, role = options["email"], options["role"]
        if (role or options["remove"]) and not email:
            raise CommandError("--email is required when changing membership.")
        if email and bool(role) == bool(options["remove"]):
            raise CommandError("Choose exactly one of --role or --remove.")
        support = {"support_view", "support_email"}
        managed_codes = support | {"support_manage", "support_billing"}
        managed_permissions = Permission.objects.filter(
            content_type__app_label="trainer",
            content_type__model="accountpolicy",
            codename__in=managed_codes,
        )
        for name, codes in (
            ("Support", support),
            ("Account Operators", support | {"support_manage", "support_billing"}),
        ):
            group, _ = Group.objects.get_or_create(name=name)
            permissions = Permission.objects.filter(
                content_type__app_label="trainer",
                content_type__model="accountpolicy",
                codename__in=codes,
            )
            if permissions.count() != len(codes):
                raise RuntimeError("Support permissions are missing; run migrate first.")
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"Configured {name}"))
        if email:
            users = get_user_model().objects.select_for_update().filter(email__iexact=email)
            if users.count() != 1:
                raise CommandError("Expected exactly one existing account for that email.")
            user = users.get()
            if user.is_superuser:
                raise CommandError("This command does not modify superusers.")
            allowed_codes = support if role == "Support" else managed_codes if role else set()
            if (
                user.groups.exclude(name__in=["Support", "Account Operators"])
                .filter(permissions__in=managed_permissions.exclude(codename__in=allowed_codes))
                .exists()
            ):
                raise CommandError(
                    "Another group grants permissions beyond the requested support role; "
                    "remove that membership before changing the support role."
                )
            user.groups.remove(*Group.objects.filter(name__in=["Support", "Account Operators"]))
            user.user_permissions.remove(*managed_permissions)
            if role:
                user.groups.add(Group.objects.get(name=role))
            user.is_staff = bool(role)
            user.save(update_fields=["is_staff"])
            self.stdout.write(
                self.style.SUCCESS("Support membership updated. MFA is still required.")
            )
