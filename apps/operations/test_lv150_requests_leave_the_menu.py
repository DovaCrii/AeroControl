"""LV-150 paso 1: "Solicitudes SIGO" sale del menú, y nada más se retira.

Procedimiento de `LV-78` y `LV-103`: primero sin superficie propia, después
congelado, y sólo al final se borra si nadie lo echa de menos. Lo que estos
tests sujetan es la mitad que se puede romper sin darse cuenta — que el retiro
**no** se llevó por delante ninguna de las cinco puertas que quedan, y que el
descubrimiento se movió a la ficha del plan en vez de desaparecer.

Condición de reversión, escrita para la próxima persona: si en un mes hay al
menos una solicitud creada en producción, esto se revierte en vez de avanzar al
paso 2.
"""

import math
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.models import FlightRequest
from apps.registry.models import CostCenter

BASE_HTML = Path(settings.BASE_DIR) / "templates" / "base.html"
LAT, LON = -31.918, -70.949


def _circle(name):
    ring = []
    for step in range(24):
        angle = 2 * math.pi * step / 24
        ring.append([LON + 0.005 * math.cos(angle), LAT + 0.005 * math.sin(angle), 0])
    ring.append(list(ring[0]))
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "extended_data": None,
        "extras": [],
    }


@pytest.fixture
def plan(db):
    center = CostCenter.objects.create(code="CC738", name="Los Pelambres")
    owner = User.objects.create_user("owner", password="password")
    plan = GeoPlan.objects.create(
        title="CC738 · CG-01", cost_center=center, created_by=owner
    )
    document = empty_document()
    document["children"].append(_circle("Quebrada km 13.760"))
    plan.current_version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=owner,
    )
    plan.save()
    return plan


def _client(username, *codenames):
    user = User.objects.create_user(username, password="password")
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    client = Client()
    assert client.login(username=username, password="password")
    return client


def _request_for(plan, title="Solicitud de prueba"):
    return FlightRequest.objects.create(
        title=title,
        cost_center=plan.cost_center,
        source_plan=plan,
        area_name="Quebrada km 13.760",
        # El centro y el radio son obligatorios: una solicitud sin ellos no es
        # presentable, que es exactamente lo que la constraint dice.
        center_lat=LAT,
        center_lon=LON,
        radius_m=557,
    )


# -- el retiro -------------------------------------------------------------


def test_the_link_is_commented_out_and_not_deleted():
    """Reversible en una línea, que es lo que hace de esto un paso 1 y no una
    amputación. Se lee el archivo porque el enlace comentado no se renderiza y
    ninguna página lo puede mostrar."""
    markup = BASE_HTML.read_text(encoding="utf-8")
    commented = re.findall(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", markup, flags=re.DOTALL
    )

    assert "flight-request-list" in "\n".join(commented), (
        "el enlace no está dentro de un bloque comentado: o se borró, o volvió"
    )
    # Y fuera de los comentarios no queda ninguno.
    visible = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", markup, flags=re.DOTALL
    )
    assert "flight-request-list" not in visible


def test_the_menu_still_has_more_icons_than_the_guard_requires():
    """`test_r103_nav_icons_are_distinct` exige al menos 15 entradas para no
    pasar en verde sin haber leído nada. Retirar una baja el número, y esto es
    lo que avisa si un retiro futuro lo deja por debajo del piso."""
    from apps.core.test_r103_nav_icons_are_distinct import _entries

    assert len(_entries()) >= 15


@pytest.mark.django_db
def test_the_url_is_still_registered_and_answers(plan):
    """Sobreviven cinco puertas: el panel, el expediente del permiso, el
    redirect del POST de separar, la navegación interna de la ficha y el enlace
    contextual del plan. Ninguna funciona si la ruta se cae."""
    client = _client("reader", "view_flightrequest")

    assert client.get(reverse("flight-request-list")).status_code == 200


@pytest.mark.django_db
def test_reading_the_list_still_needs_the_view_permission(plan):
    """El 403 obligatorio de AGENTS.md: retirar el enlace no relaja el permiso."""
    client = _client("nobody")

    assert client.get(reverse("flight-request-list")).status_code == 403


# -- el descubrimiento se movió, no desapareció ----------------------------


@pytest.mark.django_db
def test_the_plan_offers_the_requests_it_originated(plan):
    _request_for(plan)
    client = _client("reader", "view_geoplan", "view_costcenter", "view_flightrequest")

    response = client.get(reverse("geo-plan-detail", args=[plan.pk]))
    body = response.content.decode()

    assert response.context["request_count"] == 1
    assert f"{reverse('flight-request-list')}?plan={plan.pk}" in body
    assert "1 solicitud de este plan" in body


@pytest.mark.django_db
def test_a_plan_with_no_requests_offers_no_link(plan):
    """Ofrecer "0 solicitudes" sería un enlace a una lista vacía."""
    client = _client("reader", "view_geoplan", "view_costcenter", "view_flightrequest")

    body = client.get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    assert "de este plan" not in body


@pytest.mark.django_db
def test_the_count_is_zero_without_the_view_permission(plan):
    """Un enlace que termina en 403 enseña a desconfiar de la pantalla
    (LV-130), así que el gate está en la vista y no sólo en la plantilla."""
    _request_for(plan)
    client = _client("reader", "view_geoplan", "view_costcenter")

    response = client.get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.context["request_count"] == 0
    assert "de este plan" not in response.content.decode()


@pytest.mark.django_db
def test_an_archived_request_is_not_counted(plan):
    request_obj = _request_for(plan)
    request_obj.is_active = False
    request_obj.save(update_fields=["is_active"])
    client = _client("reader", "view_geoplan", "view_costcenter", "view_flightrequest")

    response = client.get(reverse("geo-plan-detail", args=[plan.pk]))

    assert response.context["request_count"] == 0


# -- el filtro al que apunta el enlace -------------------------------------


@pytest.mark.django_db
def test_the_filter_shows_only_this_plans_requests(plan):
    """Llegar por el enlace y ver las solicitudes de *otros* planes sería un
    enlace que no cumple lo que ofrece."""
    mine = _request_for(plan)
    other_plan = GeoPlan.objects.create(
        title="CC738 · otro",
        cost_center=plan.cost_center,
        created_by=plan.created_by,
    )
    theirs = _request_for(other_plan, title="De otro plan")
    client = _client("reader", "view_flightrequest")

    body = client.get(
        reverse("flight-request-list"), {"plan": str(plan.pk)}
    ).content.decode()

    assert mine.title in body
    assert theirs.title not in body


@pytest.mark.django_db
def test_a_malformed_plan_filter_is_empty_and_not_a_500(plan):
    """Vacío y no "sin filtro": el listado dice que nada coincide y ofrece
    limpiarlo, mientras mostrar todas afirmaría que ésas son las del plan
    pedido. `lookup_by_pk` es lo que evita el 500 sobre un valor que no es UUID.
    """
    _request_for(plan)
    client = _client("reader", "view_flightrequest")

    response = client.get(reverse("flight-request-list"), {"plan": "not-a-uuid"})

    assert response.status_code == 200
    assert list(response.context["objects"]) == []
    assert response.context["is_filtered"] is True
