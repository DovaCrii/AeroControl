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
        "add_geoplan",
        "change_geoplan",
        "view_geoplan",
        # Per-resource assignments (OPS-1). The movement log is append-only, so
        # only view is ever granted for it.
        "add_operatorassignment",
        "change_operatorassignment",
        "view_operatorassignment",
        "add_aircraftassignment",
        "change_aircraftassignment",
        "view_aircraftassignment",
        "view_resourcemovementlog",
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
        # Operator qualifications / ratings and their catalog (B4.3): Compliance
        # tracks credentials, so it manages both. Previously only a superuser
        # could create a Qualification at all.
        "add_qualification",
        "change_qualification",
        "view_qualification",
        "add_qualificationtype",
        "change_qualificationtype",
        "view_qualificationtype",
        # Compliance approves flight-planning geo plans; it does not draw them.
        "view_geoplan",
        "approve_geoplan",
    },
    "Maintenance": {
        "add_maintenancerecord",
        "change_maintenancerecord",
        "view_maintenancerecord",
    },
    # Spelled out on purpose. This used to be every permission whose codename
    # starts with "view_", which quietly handed the lowest role the API tokens,
    # the user list, the sessions, the audit trail, the job history and the
    # tenant configuration. A read-only role reads the operational record, not
    # the administration of the system.
    "Viewer": {
        "view_costcenter",
        "view_aircraft",
        "view_operator",
        "view_assignment",
        "view_operatorassignment",
        "view_aircraftassignment",
        "view_resourcemovementlog",
        "view_qualification",
        "view_qualificationtype",
        "view_document",
        "view_documenttype",
        "view_alert",
        "view_alertrule",
        "view_maintenancerecord",
        "view_maintenancehistory",
        "view_flightpermission",
        "view_flightrecord",
        "view_permissionhistory",
        "view_kanbanboard",
        "view_kanbanstage",
        "view_kanbantask",
        "view_kanbanlabel",
        "view_kanbantasklabel",
        "view_kanbanchecklistitem",
        "view_geoplan",
    },
}


class Command(BaseCommand):
    help = "Create or update the standard AeroControl authorization groups."

    def handle(self, *args, **options):
        all_permissions = Permission.objects.all()
        for name, codenames in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(all_permissions.filter(codename__in=codenames))
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
