"""LV-81b (mitad de presentación): una póliza vencida no se dibuja como vigente.

La ficha de la aeronave afirmaba dos cosas incompatibles al mismo tiempo: la
insignia decía "Vencida" y la escalera mostraba **"Póliza vigente" alcanzado**.
De las dos, la que se lee de un vistazo es la escalera.

Se corrige **lo que se muestra**, no el dato. Mover el estado guardado por fecha
es la misma decisión que `LV-83` tomó para los permisos —estado terminal nuevo
más un trabajo diario que lo aplica— y está pendiente de acordarse una vez para
los dos; derivarlo al dibujar no escribe nada y no puede desincronizarse.

El caso que obliga a pensarlo dos veces es el último test: la escalera dibuja
siempre los tres pasos, así que "el último paso es 'vigente'" **no** significa
que se haya llegado a él.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import Aircraft

TODAY = timezone.localdate()


def _aircraft(status, expiry):
    aircraft = Aircraft(
        registration="RPA-81B",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        insurance_status=status,
        insurance_expiry=expiry,
    )
    return aircraft


@pytest.mark.django_db
def test_a_policy_in_force_reads_as_reached():
    aircraft = _aircraft(Aircraft.INSURANCE_STATUS_ACTIVE, TODAY + timedelta(days=90))

    last = aircraft.insurance_steps()[-1]

    assert last["state"] == "current"


@pytest.mark.django_db
def test_a_lapsed_policy_stops_claiming_to_be_in_force():
    """El caso de la ficha: fecha pasada, estado todavía "vigente"."""
    aircraft = _aircraft(Aircraft.INSURANCE_STATUS_ACTIVE, TODAY - timedelta(days=5))

    last = aircraft.insurance_steps()[-1]

    assert last["state"] == "blocked"
    assert str(last["label"]) != str(
        dict(Aircraft.INSURANCE_STATUS_CHOICES)[Aircraft.INSURANCE_STATUS_ACTIVE]
    )


@pytest.mark.django_db
def test_the_earlier_steps_still_show_as_covered():
    """Que la póliza haya vencido no borra que el trámite se hizo."""
    aircraft = _aircraft(Aircraft.INSURANCE_STATUS_ACTIVE, TODAY - timedelta(days=5))

    steps = aircraft.insurance_steps()

    assert [step["state"] for step in steps[:-1]] == ["done", "done"]


@pytest.mark.django_db
def test_a_filing_still_in_sigo_is_never_marked_lapsed():
    """La escalera dibuja los tres pasos siempre, así que mirar el último en vez
    del estado marcaría como vencida una póliza que **nunca estuvo vigente** --
    con una fecha vieja de un intento anterior, además."""
    aircraft = _aircraft(Aircraft.INSURANCE_STATUS_FILED, TODAY - timedelta(days=5))

    steps = aircraft.insurance_steps()

    assert steps[-1]["state"] == "pending"
    assert [step["state"] for step in steps] == ["done", "current", "pending"]


@pytest.mark.django_db
def test_nothing_on_file_is_untouched():
    aircraft = _aircraft(Aircraft.INSURANCE_STATUS_MISSING, None)

    assert [step["state"] for step in aircraft.insurance_steps()] == [
        "pending",
        "pending",
        "pending",
    ]
