"""LV-369: quien salió de la empresa y el padrón «al corte» del informe mensual.

El informe mensual describe una **fecha**. `MAPPING.md` (§ «El corte temporal»)
dice que el padrón al corte es una cota superior y que archivar a alguien lo saca
también de los informes anteriores, porque no hay historial de `is_active`. Para
quien tiene **fecha de salida** sí se sabe cuándo se fue, y el padrón al corte pasa
a ser exacto en el borde:

- salió **después** del corte → estaba ese día, cuenta;
- salió **en** el corte o antes → no cuenta;
- sin salida registrada (todos los datos que ya existen) → igual que siempre.

La diferencia con «hoy» es deliberada: el panel y el catastro de hoy no muestran a
un ex colaborador, y el informe de un mes en que aún estaba, sí.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.dashboard.views import panel_readiness
from apps.registry.models import CostCenter, Operator
from apps.reporting.builder import build

TODAY = timezone.localdate()
CUTOFF = TODAY - timedelta(days=10)


def _person(code, credential_days=100):
    person = Operator.objects.create(
        employee_id=f"RUT-{code}",
        full_name=f"Persona {code}",
        credential_expiry=TODAY + timedelta(days=credential_days),
    )
    # Cargada hace 60 días: existe en el corte (`created_at__date <= corte`).
    Operator.objects.filter(pk=person.pk).update(
        created_at=timezone.now() - timedelta(days=60)
    )
    person.refresh_from_db()
    return person


def _credentials(cutoff):
    cards = {c["key"]: c for c in panel_readiness(cutoff)["readiness"]}
    return cards["credentials"]["total"], cards["credentials"]["count"]


@pytest.mark.django_db
class TestThePopulationAtTheCutoff:
    def test_without_departures_nothing_changes(self):
        """Regresión: los datos que ya existen (sin `left_company_on`) dan lo mismo."""
        _person("1")
        _person("2")
        archived = _person("3")
        archived.is_active = False
        archived.save()

        assert _credentials(CUTOFF) == (2, 2)
        assert _credentials(TODAY) == (2, 2)

    def test_someone_who_left_after_the_cutoff_counts_in_it(self):
        _person("1")
        later = _person("2")
        later.register_departure(left_on=CUTOFF + timedelta(days=1))

        assert _credentials(CUTOFF)[0] == 2

    def test_someone_who_left_on_the_cutoff_does_not_count(self):
        _person("1")
        same_day = _person("2")
        same_day.register_departure(left_on=CUTOFF)

        assert _credentials(CUTOFF)[0] == 1

    def test_someone_who_left_before_the_cutoff_does_not_count(self):
        _person("1")
        earlier = _person("2")
        earlier.register_departure(left_on=CUTOFF - timedelta(days=1))

        assert _credentials(CUTOFF)[0] == 1

    def test_the_day_after_the_departure_is_the_first_one_without_them(self):
        """El borde exacto, en las dos puertas del mismo día."""
        _person("1")
        person = _person("2")
        left = TODAY - timedelta(days=5)
        person.register_departure(left_on=left)

        assert _credentials(left - timedelta(days=1))[0] == 2
        assert _credentials(left)[0] == 1
        assert _credentials(left + timedelta(days=1))[0] == 1

    def test_today_never_counts_them(self):
        """Con la fecha de hoy es el padrón de hoy: el panel no cambia."""
        _person("1")
        person = _person("2")
        person.register_departure(left_on=TODAY)

        assert _credentials(TODAY)[0] == 1

    def test_the_credential_numbers_follow_the_same_population(self):
        _person("1", credential_days=100)
        lapsed = _person("2", credential_days=-20)  # vencida antes del corte
        lapsed.register_departure(left_on=CUTOFF + timedelta(days=1))

        cards = {c["key"]: c for c in panel_readiness(CUTOFF)["readiness"]}

        assert cards["credentials"]["total"] == 2
        # Al corte, la credencial de quien salió después aún estaba vencida.
        assert cards["credentials"]["lapsed"] == 1

    def test_an_archived_person_without_a_departure_is_still_out_of_past_reports(
        self,
    ):
        """Lo que `MAPPING.md` ya dejaba dicho para el archivado a secas, intacto:
        sin fecha de salida no se sabe cuándo se fue y no se reconstruye."""
        _person("1")
        archived = _person("2")
        archived.is_active = False
        archived.save()

        assert _credentials(CUTOFF)[0] == 1

    def test_the_cost_center_filter_keeps_working(self):
        center = CostCenter.objects.create(code="CC738", name="MLP")
        person = _person("1")
        person.cost_center = center
        person.save()
        person.register_departure(left_on=CUTOFF + timedelta(days=2))

        cards = {
            c["key"]: c
            for c in panel_readiness(CUTOFF, cost_center=center)["readiness"]
        }

        assert cards["credentials"]["total"] == 1


@pytest.mark.django_db
def test_the_monthly_payload_uses_the_same_population():
    """El informe y el panel no pueden discrepar: el payload llama a la misma función."""
    _person("1")
    later = _person("2")
    later.register_departure(left_on=CUTOFF + timedelta(days=1))
    period = CUTOFF.replace(day=1)

    payload, _missing = build(period, cutoff=CUTOFF)

    assert payload["kpis"]["operators_total"]["value"] == 2
