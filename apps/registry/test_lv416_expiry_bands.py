"""LV-416: el semáforo de LV-413 también en el seguro de las aeronaves y en las habilitaciones.

Las dos listas pintaban en ámbar toda fecha futura (también un seguro que vence en 2029).
Ahora los tres usan la misma insignia (`registry/_expiry_badge.html`) y la misma escala
(`selectors.expiry_band`, cortes 30/60 de `kpis.permit_band`).

Las afirmaciones de presentación comparan contra el objeto (`EXPIRY_BAND_CSS`) y se acotan
al cuerpo de la tabla (lección de LV-118). Datos ficticios.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.core.testing import login_as
from apps.registry.models import Aircraft, Operator, Qualification, QualificationType
from apps.registry.selectors import (
    CREDENTIAL_BAND_CSS,
    EXPIRY_BAND_CSS,
    credential_band,
    expiry_band,
)

# (días hasta el vencimiento, banda esperada); `None` es «sin fecha».
EDGES = [
    (-1, "lapsed"),
    (0, "soon"),
    (30, "soon"),
    (31, "warning"),
    (60, "warning"),
    (61, "current"),
    (900, "current"),
    (None, "missing"),
]


def _today():
    return timezone.localdate()


def _rows(response):
    return response.content.decode().split('id="table-body"')[-1]


def _expiry(days):
    return None if days is None else _today() + timedelta(days=days)


def _only_band(rows, band):
    assert f'class="badge {EXPIRY_BAND_CSS[band]}"' in rows
    for other in set(EXPIRY_BAND_CSS.values()) - {EXPIRY_BAND_CSS[band]}:
        assert f'class="badge {other}"' not in rows


class TestSingleSource:
    def test_credential_names_are_the_same_objects(self):
        assert credential_band is expiry_band
        assert CREDENTIAL_BAND_CSS is EXPIRY_BAND_CSS

    @pytest.mark.parametrize(("days", "band"), EDGES)
    def test_the_edges(self, days, band):
        assert expiry_band(_expiry(days), _today())[0] == band

    def test_every_band_has_a_style(self):
        css = "".join(
            (Path(settings.BASE_DIR) / "static" / "css" / name).read_text("utf-8")
            for name in ("app.css", "expiry-band.css")
        )
        for name in EXPIRY_BAND_CSS.values():
            assert f".badge.{name}" in css, name


@pytest.mark.django_db
class TestAircraftInsurance:
    URL = reverse("aircraft-list")

    @pytest.mark.parametrize(("days", "band"), EDGES[:-1])
    def test_the_row_carries_the_band_of_its_expiry(self, days, band):
        Aircraft.objects.create(registration="CC-T416", insurance_expiry=_expiry(days))
        rows = _rows(login_as("view_aircraft").get(self.URL))
        _only_band(rows, band)

    def test_a_far_expiry_is_never_amber(self):
        Aircraft.objects.create(registration="CC-T417", insurance_expiry=_expiry(900))
        rows = _rows(login_as("view_aircraft").get(self.URL))
        assert "badge sev-caution" not in rows
        assert "badge sev-warning" not in rows

    def test_days_remaining_are_in_the_close_bands(self):
        Aircraft.objects.create(registration="CC-T418", insurance_expiry=_expiry(45))
        rows = _rows(login_as("view_aircraft").get(self.URL))
        assert "· 45 " in rows

    def test_the_state_comes_from_the_aircraft(self):
        aircraft = Aircraft.objects.create(
            registration="CC-T419", insurance_expiry=_expiry(10)
        )
        assert aircraft.insurance_state["band"] == "soon"
        assert aircraft.insurance_state["days"] == 10
        assert aircraft.insurance_state["css"] == EXPIRY_BAND_CSS["soon"]

    def test_no_expiry_and_status_active_is_neutral(self):
        Aircraft.objects.create(registration="CC-T420")
        aircraft = Aircraft.objects.get(registration="CC-T420")
        assert aircraft.insurance_state["band"] == "missing"

    def test_403_without_view_aircraft(self):
        assert login_as().get(self.URL).status_code == 403


@pytest.mark.django_db
class TestQualificationsList:
    URL = reverse("qualification-list")

    def _operator(self, days):
        operator = Operator.objects.create(
            full_name="Operador Prueba",
            employee_id="E-416",
            credential_expiry=_expiry(days),
        )
        Qualification.objects.create(
            operator=operator,
            qualification_type=QualificationType.objects.create(
                code="rpas", name="RPAS"
            ),
            issue_date=_today() - timedelta(days=100),
        )
        return operator

    @pytest.mark.parametrize(("days", "band"), EDGES)
    def test_the_credential_cell_carries_the_band(self, days, band):
        self._operator(days)
        rows = _rows(login_as("view_qualification").get(self.URL))
        _only_band(rows, band)

    def test_no_date_is_worded_not_a_bare_dash(self):
        self._operator(None)
        rows = _rows(login_as("view_qualification").get(self.URL))
        assert gettext("No date") in rows

    def test_a_lapsed_credential_keeps_its_word_and_icon(self):
        self._operator(-5)
        rows = _rows(login_as("view_qualification").get(self.URL))
        assert "⚠ " + gettext("Overdue") in rows

    def test_403_without_view_qualification(self):
        assert login_as().get(self.URL).status_code == 403


@pytest.mark.django_db
def test_the_three_lists_load_the_shared_stylesheet():
    for name, perm in (
        ("aircraft-list", "view_aircraft"),
        ("operator-list", "view_operator"),
        ("qualification-list", "view_qualification"),
    ):
        content = login_as(perm).get(reverse(name)).content.decode()
        assert "css/expiry-band.css" in content, name
