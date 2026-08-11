"""LV-73 [bug de pérdida de datos]: los `<input type="date">` mostraban vacío.

`AeroModelForm` cambia `input_type` a `date`/`datetime-local`/`time` para usar los
selectores nativos del navegador, pero no fijaba el `format` del widget. Django
entonces emitía la fecha en el formato del locale (`value="21/08/2026"` bajo
`LANGUAGE_CODE="es"`) y **un `<input type="date">` sólo acepta ISO**, así que el
navegador descartaba el valor y el campo aparecía en blanco.

El daño real no era estético: al guardar, el navegador envía vacío ese campo, así
que **editar cualquier otro dato de la aeronave borraba la vigencia del seguro**
en silencio — y con ella su alerta, su fila en el calendario y su aporte al
reporte de cumplimiento. Encontrado en el demo con RPA-2002 (seguro al
2026-08-21 mostrándose vacío).
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.registry.forms import AircraftForm
from apps.registry.models import Aircraft, CostCenter

TODAY = date(2026, 8, 11)


@pytest.fixture
def aircraft(db):
    cost_center = CostCenter.objects.create(code="CC1", name="One")
    return Aircraft.objects.create(
        registration="RPA-2002",
        type="RPAS",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
        insurance_expiry=date(2026, 8, 21),
    )


@pytest.mark.django_db
def test_a_date_renders_in_iso_so_the_browser_accepts_it(aircraft):
    """The regression guard: any locale-formatted value here is silently
    discarded by the browser."""
    html = AircraftForm(instance=aircraft).as_p()

    assert 'value="2026-08-21"' in html
    # The Chilean format is what the bug emitted; it must not come back.
    assert "21/08/2026" not in html


@pytest.mark.django_db
def test_editing_another_field_does_not_wipe_the_insurance_date(aircraft, client):
    """The actual data loss, end to end: open the edit form, change only the
    model name, save -- the insurance expiry must survive.

    Submits exactly what the browser would send for each rendered field, so a
    value the browser would have dropped shows up here as a cleared date.
    """
    User.objects.create_superuser("admin", "a@test.com", "password")
    assert client.login(username="admin", password="password")

    form = AircraftForm(instance=aircraft)
    payload = {}
    for name, field in form.fields.items():
        value = form[name].value()
        if value in (None, ""):
            continue
        # An <input type="date"> only submits a value it could parse; anything
        # else arrives empty, which is the bug being guarded.
        if hasattr(field.widget, "input_type") and field.widget.input_type == "date":
            payload[name] = value if str(value).count("-") == 2 else ""
        else:
            payload[name] = value
    payload["model"] = "M350"

    response = client.post(
        reverse("aircraft-update", args=[aircraft.pk]), payload, follow=True
    )

    assert response.status_code == 200
    aircraft.refresh_from_db()
    assert aircraft.model == "M350"  # the edit landed
    assert aircraft.insurance_expiry == date(2026, 8, 21)  # ...and the date survived


@pytest.mark.django_db
def test_an_iso_date_typed_by_the_browser_still_saves(aircraft):
    """The other half: the es locale's DATE_INPUT_FORMATS includes %Y-%m-%d, so
    what the native picker submits must validate. If a future settings change
    dropped ISO from that list, this fails instead of the date silently not
    updating."""
    renewed = TODAY + timedelta(days=400)
    form = AircraftForm(
        data={
            "registration": aircraft.registration,
            "type": aircraft.type,
            "model": aircraft.model,
            "manufacturer": aircraft.manufacturer,
            "cost_center": aircraft.cost_center_id,
            "status": "active",
            "current_location": "headquarters",
            "insurance_expiry": renewed.isoformat(),
        },
        instance=aircraft,
    )

    assert form.is_valid(), form.errors
    assert form.save().insurance_expiry == renewed


@pytest.mark.django_db
def test_time_and_datetime_widgets_get_iso_formats_too(db):
    """Same bug class: a localized time or datetime is discarded by
    `<input type="time">` / `type="datetime-local"`."""
    from apps.operations.forms import FlightRecordForm

    for name, field in FlightRecordForm().fields.items():
        input_type = getattr(field.widget, "input_type", None)
        if input_type == "time":
            assert field.widget.format == "%H:%M", name
        elif input_type == "datetime-local":
            assert field.widget.format == "%Y-%m-%dT%H:%M", name
