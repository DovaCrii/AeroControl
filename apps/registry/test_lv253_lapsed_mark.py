"""LV-253: una sola forma de decir «vencido», y la ficha del operador la dice.

Nueve insignias de vencido usaban `bg-danger` a secas —el mismo rojo que «Rechazado»
o «Insuficiente»— y la ficha del operador no marcaba la credencial DGAC vencida,
aunque la lista sí. Ahora todas son `badge sev-critical` con **⚠**, sobre los mismos
tokens que la fila crítica del panel (`LV-246`).

Las afirmaciones se acotan a la región que se afirma: el armazón de la página tiene
su propio `sev-critical` (el contador de alertas), así que buscarlo en toda la página
podría salir verde por el vecino (lección de `LV-118` en `AGENTS.md`).
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.registry.models import Aircraft, CostCenter, Operator

LAPSED_BADGE = 'class="badge sev-critical">⚠ '


def _operator(**extra):
    cost_center = CostCenter.objects.create(code="CC-253", name="Faena 253")
    return Operator.objects.create(
        employee_id="OP-253",
        full_name="Piloto Vencido",
        cost_center=cost_center,
        **extra,
    )


@pytest.mark.django_db
class TestTheOperatorFichaMarksTheCredential:
    def _body(self, client, operator):
        content = client.get(
            reverse("operator-detail", args=[operator.pk])
        ).content.decode()
        return content.split('<div class="card p-4">', 1)[-1]

    def test_a_lapsed_credential_is_marked_in_red(self, admin_client):
        operator = _operator(credential_expiry=timezone.localdate() - timedelta(days=3))

        body = self._body(admin_client, operator)

        assert "data-credential-lapsed" in body
        assert LAPSED_BADGE + gettext("DGAC credential lapsed") in body

    def test_a_credential_in_force_carries_no_mark(self, admin_client):
        operator = _operator(
            credential_expiry=timezone.localdate() + timedelta(days=30)
        )

        assert "data-credential-lapsed" not in self._body(admin_client, operator)

    def test_no_date_on_file_is_unknown_not_lapsed(self, admin_client):
        """`LV-29`: sin fecha es «nunca se ingresó», no «vencida»."""
        operator = _operator()

        assert "data-credential-lapsed" not in self._body(admin_client, operator)


@pytest.mark.django_db
class TestTheListsUseTheSameMark:
    def test_the_operator_row(self, admin_client):
        _operator(credential_expiry=timezone.localdate() - timedelta(days=3))

        content = admin_client.get(reverse("operator-list")).content.decode()
        rows = content.split('id="table-body"')[-1]

        assert LAPSED_BADGE + gettext("Overdue") in rows

    def test_the_aircraft_row(self, admin_client):
        Aircraft.objects.create(
            registration="RPA-253",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            status="active",
            insurance_expiry=timezone.localdate() - timedelta(days=3),
        )

        content = admin_client.get(reverse("aircraft-list")).content.decode()
        rows = content.split('id="table-body"')[-1]

        assert LAPSED_BADGE + gettext("Overdue") in rows


def test_the_lapsed_badge_class_exists_in_the_stylesheet():
    """Guardián contra otra clase fantasma (`LV-246`): la insignia tiene que tener
    regla en `app.css`, no sólo nombre en la plantilla."""
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
        encoding="utf-8"
    )
    assert ".badge.sev-critical" in css
