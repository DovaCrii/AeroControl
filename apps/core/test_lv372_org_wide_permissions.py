"""LV-372 (F-08, fase 0): los permisos «de toda la organización» no están en ningún rol.

Con dos empresas, estos permisos dan acceso a datos de **todas**: el rastro de auditoría y
el historial de trabajos no llevan empresa, y crear empresas, membresías, centros, aeronaves,
operadores o alertas manuales fuera del alcance de una sola empresa es administración de
la organización. Hoy sólo Administrator los tiene (recibe todos). Si alguien los agrega a
un rol de `bootstrap_roles.py`, esta prueba falla y obliga a decidir antes si ese rol pasa
a ser «de toda la organización» o si el permiso necesita antes aislamiento por empresa.
"""

import pytest
from django.contrib.auth.models import Permission

from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS

ORGANIZATION_WIDE = {
    "view_auditevent",
    "view_jobrun",
    "add_operationaltenant",
    "change_operationaltenant",
    "add_tenantmembership",
    "change_tenantmembership",
    "change_importbatch",
    "add_alert",
    "add_costcenter",
    "add_aircraft",
    "add_operator",
}


def test_no_role_but_administrator_holds_an_organization_wide_permission():
    offenders = {
        role: sorted(codenames & ORGANIZATION_WIDE)
        for role, codenames in ROLE_PERMISSIONS.items()
        if codenames & ORGANIZATION_WIDE
    }
    assert offenders == {}


@pytest.mark.django_db
def test_every_listed_codename_exists():
    # Sin esto, un permiso renombrado dejaría la lista vigilando un nombre que ya no existe.
    existing = set(Permission.objects.values_list("codename", flat=True))
    assert ORGANIZATION_WIDE <= existing


@pytest.mark.django_db
def test_administrator_still_holds_them_all():
    from django.contrib.auth.models import Group
    from django.core.management import call_command

    call_command("bootstrap_roles", verbosity=0)
    held = set(
        Group.objects.get(name="Administrator").permissions.values_list(
            "codename", flat=True
        )
    )
    assert ORGANIZATION_WIDE <= held
