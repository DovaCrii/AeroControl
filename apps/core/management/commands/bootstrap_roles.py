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
        # R8.1: Operations flies, so Operations is who reviews the weather
        # before a flight. Append-only, like the movement log above -- add and
        # view are granted, change and delete never are.
        "add_weatherreview",
        "view_weatherreview",
        # R7.4: Operations records the deliverable's metrics; validating and
        # releasing it belongs to Compliance, so no `change` here.
        "add_deliverable",
        "view_deliverable",
        # R7.6: Operations reports what happened in the field (an incident, a
        # reflight); the analysis and the closure are Compliance's.
        "add_nonconformity",
        "view_nonconformity",
        # Per-resource assignments (OPS-1). The movement log is append-only, so
        # only view is ever granted for it.
        "add_operatorassignment",
        "change_operatorassignment",
        "view_operatorassignment",
        "add_aircraftassignment",
        "change_aircraftassignment",
        "view_aircraftassignment",
        "view_resourcemovementlog",
        # R9: la solicitud de vuelo SIGO es preparación operacional -- quien
        # vuela es quien la arma, la presenta y la persigue.
        "add_flightrequest",
        "change_flightrequest",
        "view_flightrequest",
        # El historial es append-only: sólo se lee, igual que el log de
        # movimientos y por la misma razón.
        "view_flightrequesthistory",
        # Las notas de cambio también: se agregan y se leen, nunca se editan
        # ni se borran -- mismo trato que `weatherreview`, y es lo que las hace
        # servir como traza.
        "add_flightrequestnote",
        "view_flightrequestnote",
        # Los pares (área de trabajo, objetivo) son filas hijas que se agregan y
        # se quitan de la tabla mientras se arma la solicitud; `change` no
        # existe como acto -- se quita el par equivocado y se pone el correcto.
        "add_flightrequestworkitem",
        "delete_flightrequestworkitem",
        "view_flightrequestworkitem",
        # R9.2: el catálogo de aeródromos lo completa quien opera, porque es
        # quien tiene la carta AIP al frente cuando confirma un AMC.
        "add_aerodrome",
        "change_aerodrome",
        "view_aerodrome",
        # R9.3: los dos vocabularios de SIGO. Se sabe que están incompletos
        # (las capturas venían cortadas), así que agregar el valor que falte
        # tiene que poder hacerse sin desplegar.
        "add_workareatype",
        "change_workareatype",
        "view_workareatype",
        "add_flightobjective",
        "change_flightobjective",
        "view_flightobjective",
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
        # Reads the meteorological evidence (ISO 8.1) without producing it.
        "view_weatherreview",
        # R7.4: Compliance owns the internal validation and the release gate
        # (ISO 8.6) -- the whole point is that whoever produced the survey is
        # not the one who signs it off.
        "add_deliverable",
        "change_deliverable",
        "view_deliverable",
        # R7.6: corrective action with root cause on record is Compliance's
        # own ground (ISO 10.2), same as resolving an alert with a reason.
        "add_nonconformity",
        "change_nonconformity",
        "view_nonconformity",
        # R9: lee lo que se pidió y su traza como evidencia, sin producirla --
        # el mismo trato que tiene con el plan geoespacial y la revisión
        # meteorológica.
        "view_flightrequest",
        "view_flightrequesthistory",
        "view_flightrequestnote",
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
        # R9: la solicitud es parte del registro operacional que este rol lee.
        # El catálogo de aeródromos no: es configuración de referencia, y la
        # lección de esta lista es justamente que un rol de sólo lectura lee la
        # operación, no la administración del sistema.
        "view_flightrequest",
        "view_flightrequesthistory",
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
