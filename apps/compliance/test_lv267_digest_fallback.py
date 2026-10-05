"""LV-267: la faena sin responsable no se queda sin aviso.

En producción (2026-10-05) 11 de 15 faenas no tenían destinatario alcanzable,
incluidas CC691 y CC861, que vencían esa semana, y el resumen las saltaba con un
«skipped»: la función existía y no llegaba a nadie. El respaldo es el grupo
Dirección, el mismo que ya recibe los avisos de infraestructura.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.utils.translation import gettext

import pytest

from apps.compliance.test_alert_digest import _qualification, cost_center  # noqa: F401
from apps.core.groups import REPORT_RECIPIENTS, direction_emails
from apps.core.models import JobRun

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _outbox(settings):
    settings.MAILERS = {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }


def _director(email, active=True, username=None):
    user = get_user_model().objects.create_user(
        username=username or email, email=email, is_active=active
    )
    Group.objects.get_or_create(name=REPORT_RECIPIENTS)[0].user_set.add(user)
    return user


def _unassign(centre):
    centre.responsible_operator = None
    centre.save(update_fields=["responsible_operator"])


class TestTheFallback:
    def test_an_unassigned_centre_goes_to_direction(self, cost_center):  # noqa: F811
        _unassign(cost_center)
        _director("direccion@example.test")
        _qualification(cost_center, 3, "Credencial urgente")

        call_command("send_alert_digest")

        assert [m.to for m in mail.outbox] == [["direccion@example.test"]]
        assert "Credencial urgente" in mail.outbox[0].body

    def test_the_mail_says_why_it_arrived(self, cost_center):  # noqa: F811
        _unassign(cost_center)
        _director("direccion@example.test")
        _qualification(cost_center, 3)

        call_command("send_alert_digest")

        body = mail.outbox[0].body
        notice = gettext(
            "This cost center has no responsible person assigned, so you receive "
            "its notice as a fallback. Assign a responsible operator or an "
            "external contact in the cost center record."
        )
        assert "FAENA-01" in body and notice in body

    def test_an_assigned_centre_does_not_bother_direction(self, cost_center):  # noqa: F811
        _director("direccion@example.test")
        _qualification(cost_center, 3)

        call_command("send_alert_digest")

        assert [m.to for m in mail.outbox] == [["ana@example.test"]]
        assert "respaldo" not in mail.outbox[0].body

    def test_nobody_anywhere_is_still_reported_as_skipped(self, cost_center):  # noqa: F811
        _unassign(cost_center)
        _qualification(cost_center, 3)

        call_command("send_alert_digest")

        assert mail.outbox == []
        assert "1 skipped" in JobRun.objects.get(command="send_alert_digest").summary

    def test_dry_run_names_the_fallback(self, cost_center, capsys):  # noqa: F811
        _unassign(cost_center)
        _director("direccion@example.test")
        _qualification(cost_center, 3)

        call_command("send_alert_digest", "--dry-run")

        out = capsys.readouterr().out
        assert mail.outbox == []
        assert "direccion@example.test" in out and "(fallback)" in out


class TestNobodyWritesTheGroupQueryByHand:
    def test_no_command_excludes_blank_emails_through_the_group(self):
        """`Group.objects.filter(...).exclude(user__email="")` descarta **el grupo
        entero** si un solo miembro no tiene correo: era la consulta de ocho
        comandos, y una persona sin correo en Dirección silenciaba a todos los
        demás. Una sola función (`direction_emails`) la hace bien."""
        from pathlib import Path

        from django.conf import settings

        offenders = [
            str(path.relative_to(settings.BASE_DIR))
            for path in (Path(settings.BASE_DIR) / "apps").rglob("*.py")
            if not path.name.startswith("test")
            and 'exclude(user__email=""' in path.read_text(encoding="utf-8")
        ]
        assert not offenders, offenders


class TestWhoIsInDirection:
    def test_inactive_users_and_blank_emails_are_left_out(self):
        _director("activo@example.test")
        _director("baja@example.test", active=False)
        _director("", username="sin-correo")
        assert direction_emails() == ["activo@example.test"]

    def test_a_user_in_two_groups_counts_once(self):
        user = _director("doble@example.test")
        Group.objects.create(name="Otro").user_set.add(user)
        assert direction_emails() == ["doble@example.test"]
