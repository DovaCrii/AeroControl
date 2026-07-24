from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from apps.core.groups import REPORT_RECIPIENTS


ROLE_PERMISSIONS = {
    "Operations": {
        "add_flightpermission",
        "change_flightpermission",
        "view_flightpermission",
        "add_flightrecord",
        "change_flightrecord",
        "delete_flightrecord",
        "view_flightrecord",
        "add_kanbantask",
        "change_kanbantask",
        "view_kanbantask",
    },
    "Compliance": {
        "add_document",
        "change_document",
        "delete_document",
        "view_document",
        "add_documenttype",
        "change_documenttype",
        "view_documenttype",
        "add_alertrule",
        "change_alertrule",
        "view_alertrule",
        "change_alert",
        "view_alert",
    },
    "Maintenance": {
        "add_maintenancerecord",
        "change_maintenancerecord",
        "view_maintenancerecord",
    },
    "Viewer": set(),
}


class Command(BaseCommand):
    help = "Create or update the standard AeroControl authorization groups."

    def handle(self, *args, **options):
        all_permissions = Permission.objects.all()
        view_permissions = all_permissions.filter(codename__startswith="view_")
        for name, codenames in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=name)
            permissions = (
                view_permissions
                if name == "Viewer"
                else all_permissions.filter(codename__in=codenames)
            )
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"Configured role: {name}"))

        administrators, _ = Group.objects.get_or_create(name="Administrator")
        administrators.permissions.set(all_permissions)
        self.stdout.write(self.style.SUCCESS("Configured role: Administrator"))

        # Notification group, not a role: it carries no permissions and only
        # decides who receives the executive report. It is created empty on
        # purpose — who belongs to it is a business decision — but it is
        # created here so setting up an environment does not depend on someone
        # reading the command's source to discover the group must exist.
        recipients, _ = Group.objects.get_or_create(name=REPORT_RECIPIENTS)
        self.stdout.write(
            self.style.SUCCESS(f"Configured notification group: {recipients.name}")
        )
