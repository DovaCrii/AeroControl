"""LV-367 (fase 6): los endpoints de la capa «Límites administrativos» y de «qué contiene esta comuna».

* `admin.json?lod=1|2`: permiso `view_airspacefeature` (LV-268), ETag y 304, peso por nivel, JSON inerte.
* `admin/<code>/contains`: zonas P/R/D/N contenidas o que tocan y aeródromos dentro, calculado contra los
  anillos COMPLETOS de BCN; con el KML sintético del repositorio (jamás el de la DGAC).
* Datos globales, sin tenant: lo declara una prueba (dos usuarios de tenants distintos ven lo mismo).
"""

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from apps.airspace import views
from apps.airspace.models import AirspaceFeature
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo import administrative_layer as layer
from apps.geo.administrative import locate

KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
LAYER = reverse("airspace-admin")
VIEW = "view_airspacefeature"


def contains_url(code):
    return reverse("airspace-admin-contains", args=[code])


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def snapshot(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)


def body(response):
    return json.loads(response.content)


# ── permisos (LV-268) ───────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [LAYER + "?lod=1", LAYER + "?lod=2", contains_url("13101"), contains_url("r13")],
)
def test_each_admin_route_is_403_without_the_exact_model_permission(snapshot, url):
    assert login_as().get(url).status_code == 403
    # Otro permiso del mismo dominio no sirve: se pide EXACTAMENTE `view_airspacefeature`.
    assert login_as("view_userweatherlocation").get(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", [LAYER, contains_url("13101")])
def test_anonymous_goes_to_the_login(snapshot, client, url):
    response = client.get(url)
    assert response.status_code == 302 and "login" in response["Location"]


@pytest.mark.django_db
def test_the_admin_views_are_mixed_with_the_model_permission_not_just_a_login():
    from apps.core.views import ModelViewPermissionRequiredMixin

    for view in (views.AirspaceAdminLayer, views.AirspaceAdminContains):
        assert issubclass(view, ModelViewPermissionRequiredMixin)
        assert view.model is AirspaceFeature


# ── admin.json ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("lod", "ceiling"), [(1, 300 * 1024), (2, 1100 * 1024)])
def test_the_served_level_weighs_what_it_was_designed_to_weigh(lod, ceiling):
    response = login_as(VIEW).get(LAYER, {"lod": lod})
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert len(response.content) <= ceiling
    data = body(response)
    assert (
        data["lod"] == lod
        and len(data["communes"]) == 346
        and len(data["regions"]) == 16
    )


@pytest.mark.django_db
def test_the_default_level_is_the_light_one_and_a_bad_level_is_a_400():
    client = login_as(VIEW)
    assert body(client.get(LAYER))["lod"] == 1
    for bad in ("0", "3", "x", "", "1.5", "-1"):
        response = client.get(LAYER, {"lod": bad})
        # `?lod=` vacío no es un entero: también se rechaza, en vez de adivinar.
        assert response.status_code == 400, bad
        assert body(response) == {"error": "invalid_lod"}


@pytest.mark.django_db
def test_the_etag_answers_304_and_changes_with_the_level():
    client = login_as(VIEW)
    first = client.get(LAYER, {"lod": 1})
    assert first["ETag"] == layer.layer_etag(1)
    assert first["Cache-Control"] == "private, no-cache"
    again = client.get(LAYER, {"lod": 1}, HTTP_IF_NONE_MATCH=first["ETag"])
    assert again.status_code == 304 and again.content == b""
    assert again["ETag"] == first["ETag"]
    assert (
        client.get(
            LAYER, {"lod": 1}, HTTP_IF_NONE_MATCH='W/"x", ' + first["ETag"]
        ).status_code
        == 304
    )
    other = client.get(LAYER, {"lod": 2})
    assert other["ETag"] != first["ETag"]
    # El ETag de un nivel no vale para el otro: el navegador no se queda con el liviano en el fino.
    assert (
        client.get(LAYER, {"lod": 2}, HTTP_IF_NONE_MATCH=first["ETag"]).status_code
        == 200
    )
    assert (
        client.get(LAYER, {"lod": 1}, HTTP_IF_NONE_MATCH='"stale"').status_code == 200
    )


@pytest.mark.django_db
def test_the_layer_is_built_once_per_process_and_is_inert_json():
    client = login_as(VIEW)
    layer.build_layer.cache_clear()
    layer.layer_bytes.cache_clear()
    client.get(LAYER, {"lod": 1})
    client.get(LAYER, {"lod": 1})
    assert layer.build_layer.cache_info().misses == 1
    assert layer.layer_bytes.cache_info().hits >= 1
    raw = client.get(LAYER, {"lod": 1}).content
    assert b"<" not in raw and b">" not in raw and b"&" not in raw


@pytest.mark.django_db
def test_the_layer_is_global_data_with_no_tenant():
    """Cartografía pública de referencia: dos personas de empresas distintas reciben los mismos bytes."""
    mine = OperationalTenant.objects.create(name="Mi empresa", slug="mi-empresa")
    other = OperationalTenant.objects.create(name="Otra empresa", slug="otra-empresa")
    one = login_as(VIEW, member_of=mine).get(LAYER, {"lod": 1}).content
    two = (
        login_as(VIEW, "view_userweatherlocation", member_of=other)
        .get(LAYER, {"lod": 1})
        .content
    )
    assert one == two
    import inspect

    source = inspect.getsource(views.AirspaceAdminLayer) + inspect.getsource(
        views.AirspaceAdminContains
    )
    assert "scope_queryset_to_tenant" not in source and "no tenant" in source


# ── contains ────────────────────────────────────────────────────────────────


def _by_code(items):
    return {item["code"]: item for item in items}


@pytest.mark.django_db
def test_a_commune_lists_the_synthetic_zone_and_aerodrome_that_lie_in_it(snapshot):
    # El aeródromo SCXA está en (-33.5, -70.7): se busca su comuna con el mismo localizador del repositorio.
    home = locate(-33.5, -70.7)
    data = body(login_as(VIEW).get(contains_url(home["code"])))
    assert data["area"] == {
        "code": home["code"],
        "name": home["comuna"],
        "kind": "commune",
        "region": home["region"],
        "communes": 1,
    }
    assert "SCXA" in _by_code(data["aerodromes"])
    assert data["tolerance_m"] == 111 and "BCN" in data["source"]
    # Los dos triángulos sintéticos de esa zona de Santiago quedan relacionados con la comuna.
    assert {"SC-R54"} <= set(_by_code(data["zones"]))
    assert all(item["relation"] in ("contained", "touches") for item in data["zones"])


@pytest.mark.django_db
def test_a_region_is_the_union_of_its_communes(snapshot):
    home = locate(-33.5, -70.7)
    region = "r" + home["code"][:-3]
    data = body(login_as(VIEW).get(contains_url(region)))
    assert data["area"]["kind"] == "region" and data["area"]["communes"] > 30
    assert data["area"]["name"] == home["region"]
    codes = set(_by_code(data["zones"])) | set(_by_code(data["aerodromes"]))
    assert {"SC-R54", "SCXA"} <= codes
    # El aeródromo de Valparaíso no está en la Región Metropolitana.
    assert "SCXB" not in codes


@pytest.mark.django_db
def test_a_far_commune_lists_nothing_and_still_answers_200(snapshot):
    punta_arenas = locate(-53.16, -70.91)
    data = body(login_as(VIEW).get(contains_url(punta_arenas["code"])))
    assert data["zones"] == [] and data["aerodromes"] == []


@pytest.mark.django_db
def test_the_undemarcated_zone_is_answered_as_what_it_is(snapshot):
    data = body(login_as(VIEW).get(contains_url("0")))
    assert data["area"]["kind"] == "undemarcated"
    assert data["area"]["name"] == "Zona sin demarcar"
    assert data["area"]["region"] == ""  # no es una región


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["999999", "r99", "abc", "13101x", "r"])
def test_an_unknown_code_is_a_404_in_json(snapshot, code):
    response = login_as(VIEW).get(contains_url(code))
    assert response.status_code == 404 and body(response) == {"error": "unknown_area"}


@pytest.mark.django_db
def test_contained_and_touches_come_from_the_full_rings_not_from_the_drawing(snapshot):
    """Una zona diminuta dentro de Santiago está contenida; una enorme que lo desborda sólo lo toca."""
    santiago = locate(-33.45, -70.65)
    assert santiago["code"] == "13101"
    tiny = AirspaceFeature.objects.get(code="SC-D66")
    tiny.geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [-70.652, -33.452],
                [-70.648, -33.452],
                [-70.648, -33.448],
                [-70.652, -33.452],
            ]
        ],
    }
    tiny.save(update_fields=["geometry"])
    huge = AirspaceFeature.objects.get(code="SC-R54")
    huge.geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [-71.5, -34.5],
                [-69.5, -34.5],
                [-69.5, -32.5],
                [-71.5, -32.5],
                [-71.5, -34.5],
            ]
        ],
    }
    huge.save(update_fields=["geometry"])
    client = login_as(VIEW)
    zones = _by_code(body(client.get(contains_url("13101")))["zones"])
    assert zones["SC-D66"]["relation"] == "contained"
    assert zones["SC-R54"]["relation"] == "touches"
    # Ordenadas: las contenidas antes que las que sólo tocan dentro de un mismo tipo, por código.
    listed = body(client.get(contains_url("13101")))["zones"]
    assert [z["kind"] for z in listed] == sorted(
        (z["kind"] for z in listed),
        key=["prohibited", "restricted", "danger", "naval"].index,
    )


@pytest.mark.django_db
def test_archived_features_never_show_up(snapshot):
    AirspaceFeature.objects.filter(code="SCXA").update(is_active=False)
    home = locate(-33.5, -70.7)
    data = body(login_as(VIEW).get(contains_url(home["code"])))
    assert "SCXA" not in _by_code(data["aerodromes"])
