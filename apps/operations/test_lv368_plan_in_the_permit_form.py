# ruff: noqa: F811, F401
"""LV-368 fase 5: lo geoespacial dentro del formulario y de la ficha del permiso.

Se fija, con datos ficticios:

- el selector de plan con su vista previa (htmx) y el recuadro «Subir un KMZ nuevo» aparecen en el
  alta **y** en la edición, según el permiso de quien mira;
- elegir o cambiar el plan desde la edición vincula por **la misma función** que la ficha (auditoría,
  bitácora `GeoPlanPermissionLink`), y nunca pisa lo escrito ni rellena con un plan de varias áreas;
- el modal de importación es `geo-plan-import` (una sola puerta): exige `add_geoplan`, no cruza de
  empresa, crea el plan en borrador como la importación normal y avisa con `geoplan-imported`;
- la ficha lee el plan vinculado con la misma lectura que la vista previa;
- el script del selector, en Node: renombra el parámetro y elige el plan recién importado.
"""

import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone, translation

from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.geo.kml.build import build_kml_bytes
from apps.geo.models import GeoPlan, GeoPlanPermissionLink
from apps.operations.forms import FlightPermissionForm
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, Operator
from apps.operations.test_lv368_plan_preview import (  # noqa: F401
    author,
    centers,
    circle_document,
    make_plan,
    tenants,
    two_circles_document,
)

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
TODAY = timezone.localdate()
FORM_PERMS = (
    "add_flightpermission",
    "change_flightpermission",
    "view_flightpermission",
)
LINK_PERMS = ("change_geoplan", "view_geoplan")


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


def make_permit(center, **overrides):
    fields = {
        "internal_folio": f"JEJ-2026-5{FlightPermission.objects.count():02d}",
        "cost_center": center,
        "purpose": "patrol",
        "valid_from": TODAY,
        "valid_until": TODAY + timedelta(days=30),
        "location": "Sitio ficticio",
        "area_type": "unpopulated",
    }
    fields.update(overrides)
    permit = FlightPermission.objects.create(**fields)
    # La edición exige operadores y aeronaves: el permiso ficticio trae uno de cada uno.
    count = FlightPermission.objects.count()
    permit.operators.add(
        Operator.objects.create(employee_id=f"E-{count}", full_name=f"Ana {count}")
    )
    permit.aircraft_fleet.add(
        Aircraft.objects.create(
            registration=f"RPA-{count}",
            type="Multirotor",
            model="M3E",
            manufacturer="DJI",
        )
    )
    return permit


def edit_payload(permit, **overrides):
    """Lo que el formulario de edición envía para este permiso, sin tocar nada más."""
    data = {
        "permission_number": permit.permission_number or "",
        "operators": [str(pk) for pk in permit.operators.values_list("pk", flat=True)],
        "aircraft_fleet": [
            str(pk) for pk in permit.aircraft_fleet.values_list("pk", flat=True)
        ],
        "cost_center": str(permit.cost_center_id),
        "purpose": permit.purpose,
        "purpose_detail": "",
        "valid_from": permit.valid_from.isoformat(),
        "valid_until": permit.valid_until.isoformat(),
        "validity_override_reason": "",
        "location": permit.location,
        "region": permit.region or "",
        "commune": permit.commune or "",
        "area_name": permit.area_name or "",
        "latitude": "" if permit.latitude is None else str(permit.latitude),
        "longitude": "" if permit.longitude is None else str(permit.longitude),
        "radius_km": "" if permit.radius_km is None else str(permit.radius_km),
        "max_altitude_m": "",
        "area_type": permit.area_type,
        "source_plan": "",
    }
    data.update(overrides)
    return data


def html_of(client, url, **params):
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    response = client.get(url, params)
    assert response.status_code == 200
    return response.content.decode()


# ── el selector, la vista previa y el modal en la página ────────────────────


@pytest.mark.django_db
class TestThePickerOnThePage:
    def test_the_create_page_wires_the_picker_to_the_preview(self, centers, tenants):
        client = login_as(*FORM_PERMS, *LINK_PERMS, "add_geoplan", member_of=tenants[0])

        html = html_of(client, reverse("permission-create"))

        assert f'hx-get="{reverse("permission-plan-preview")}"' in html
        assert "data-plan-picker-select" in html and 'id="plan-preview"' in html
        assert "js/geo/mini-map.js" in html and "js/permission-plan-picker.js" in html
        assert "vendor/leaflet/leaflet.js" in html and "css/geo-mini-map.css" in html

    def test_the_kmz_upload_is_offered_only_with_add_geoplan(self, centers, tenants):
        with_add = login_as(
            *FORM_PERMS, *LINK_PERMS, "add_geoplan", member_of=tenants[0]
        )
        without = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        html_with = html_of(with_add, reverse("permission-create"))
        html_without = html_of(without, reverse("permission-create"))

        assert "Upload a new KMZ" in html_with
        assert f'hx-get="{reverse("geo-plan-import")}"' in html_with
        assert "Upload a new KMZ" not in html_without
        assert f'hx-get="{reverse("geo-plan-import")}"' not in html_without

    def test_without_change_geoplan_there_is_no_selector_at_all(self, centers, tenants):
        # Un selector vacío, o una vista previa que termina en 403, enseña a desconfiar (LV-130).
        client = login_as(*FORM_PERMS, "view_geoplan", member_of=tenants[0])

        html = html_of(client, reverse("permission-create"))

        assert (
            "data-plan-picker-select" not in html and "js/geo/mini-map.js" not in html
        )

    def test_without_view_geoplan_the_picker_is_there_but_the_preview_is_not(
        self, centers, tenants
    ):
        client = login_as(*FORM_PERMS, "change_geoplan", member_of=tenants[0])

        html = html_of(client, reverse("permission-create"))

        assert 'id="id_source_plan"' in html
        assert "data-plan-picker-select" not in html
        assert reverse("permission-plan-preview") not in html
        assert "css/geo-mini-map.css" not in html and "js/geo/mini-map.js" not in html
        assert "when you save; what you typed is never overwritten" in html

    def test_the_edit_page_has_the_picker_too(self, centers, tenants, author):
        permit = make_permit(centers["a"])
        make_plan(centers["a"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        html = html_of(client, reverse("permission-update", args=[permit.pk]))

        assert "data-plan-picker-select" in html and "Link a geospatial plan" in html

    def test_the_label_says_replace_when_a_plan_is_already_linked(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        linked = make_plan(centers["a"], author, circle_document(), title="Actual")
        GeoPlan.objects.filter(pk=linked.pk).update(flight_permission=permit)
        make_plan(centers["a"], author, circle_document(), title="Otro")
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        html = html_of(client, reverse("permission-update", args=[permit.pk]))

        assert "Replace the linked plan" in html

    def test_the_empty_boxes_say_where_they_will_come_from(self, centers, tenants):
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        html = html_of(client, reverse("permission-create"))

        # Alta: las casillas ocultas se nombran con las palabras de la fila.
        assert "These boxes will come from the plan when you save" in html
        manual = html_of(client, reverse("permission-create"), ubicacion="manual")
        # Con `?ubicacion=manual` las casillas están y lo dicen en la propia casilla.
        assert 'placeholder="Will come from the plan"' in manual

    def test_a_filled_box_does_not_claim_to_come_from_the_plan(self, centers, tenants):
        permit = make_permit(centers["a"], commune="Salamanca")
        form = FlightPermissionForm(instance=permit, manual_location=True)

        assert "placeholder" not in form.fields["commune"].widget.attrs
        assert "placeholder" in form.fields["region"].widget.attrs

    def test_the_selector_in_the_edit_form_offers_only_the_same_cost_center_and_tenant(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        mine = make_plan(centers["a"], author, circle_document(), title="Mío")
        other_cc = make_plan(
            centers["a2"], author, circle_document(), title="Otra faena"
        )
        other_tenant = make_plan(centers["b"], author, circle_document(), title="Ajeno")
        user = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0]).user

        from apps.operations.forms import FlightPermissionUpdateForm

        form = FlightPermissionUpdateForm(instance=permit, user=user)

        offered = set(form.fields["source_plan"].queryset)
        assert mine in offered
        assert other_cc not in offered and other_tenant not in offered

    def test_the_ficha_has_no_picker_but_keeps_link_and_unlink(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        GeoPlan.objects.filter(pk=plan.pk).update(flight_permission=permit)
        client = login_as(
            "view_flightpermission",
            "view_geoplan",
            "change_geoplan",
            member_of=tenants[0],
        )

        html = html_of(client, reverse("permission-detail", args=[permit.pk]))

        assert reverse("permission-unlink-plan", args=[permit.pk]) in html
        assert 'id="tab-geo-plans"' in html


# ── editar con un plan: la misma puerta que la ficha ────────────────────────


@pytest.mark.django_db
class TestEditingWithAPlan:
    def _post(self, client, permit, **overrides):
        return client.post(
            reverse("permission-update", args=[permit.pk]),
            edit_payload(permit, **overrides),
        )

    def test_choosing_a_plan_links_it_through_the_same_door_as_the_ficha(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        response = self._post(client, permit, source_plan=str(plan.pk))

        assert response.status_code == 302, response.context["form"].errors
        plan.refresh_from_db()
        permit.refresh_from_db()
        assert plan.flight_permission_id == permit.pk
        # Lo mismo que escribe la ficha: la bitácora del vínculo, con quién lo hizo.
        link = GeoPlanPermissionLink.objects.filter(
            plan=plan, new_permission=permit
        ).get()
        assert link.changed_by_user == client.user
        # Y el relleno de huecos (sólo huecos): el centro sale del plan.
        assert permit.latitude is not None and permit.longitude is not None
        assert permit.region_source == "derived"

    def test_the_audit_keeps_the_permit_entry_and_adds_the_plan_link(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        self._post(client, permit, source_plan=str(plan.pk))

        events = AuditEvent.objects.filter(actor=client.user)
        labels = {(e.model_label, e.action) for e in events}
        assert ("geo.GeoPlan", "geoplan_linked_to_permission") in labels
        # La edición del permiso **no** se pierde: es la entrada principal de la petición.
        assert any(e.model_label == "operations.FlightPermission" for e in events)

    def test_what_the_person_typed_is_not_overwritten(self, centers, tenants, author):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        self._post(
            client,
            permit,
            source_plan=str(plan.pk),
            commune="Salamanca",
            latitude="-30.5",
            longitude="-70.5",
        )
        permit.refresh_from_db()

        assert permit.commune == "Salamanca"
        assert float(permit.latitude) == pytest.approx(-30.5)
        assert float(permit.longitude) == pytest.approx(-70.5)

    def test_a_plan_of_two_areas_links_and_fills_nothing(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, two_circles_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        self._post(client, permit, source_plan=str(plan.pk))
        permit.refresh_from_db()
        plan.refresh_from_db()

        assert plan.flight_permission_id == permit.pk
        assert permit.latitude is None and permit.longitude is None
        assert permit.region == "" and permit.commune == ""

    def test_choosing_another_plan_replaces_the_linked_one(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        old = make_plan(centers["a"], author, circle_document(), title="Viejo")
        new = make_plan(centers["a"], author, circle_document(), title="Nuevo")
        GeoPlan.objects.filter(pk=old.pk).update(flight_permission=permit)
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        self._post(client, permit, source_plan=str(new.pk))
        old.refresh_from_db()
        new.refresh_from_db()

        assert (
            old.flight_permission_id is None and new.flight_permission_id == permit.pk
        )
        # Las dos mutaciones quedan auditadas y en la bitácora del vínculo.
        actions = set(
            AuditEvent.objects.filter(actor=client.user).values_list(
                "action", flat=True
            )
        )
        assert {
            "geoplan_linked_to_permission",
            "geoplan_unlinked_from_permission",
        } <= actions
        assert GeoPlanPermissionLink.objects.filter(
            plan=old, previous_permission=permit, new_permission=None
        ).exists()

    def test_saving_without_choosing_a_plan_leaves_the_link_alone(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        GeoPlan.objects.filter(pk=plan.pk).update(flight_permission=permit)
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        self._post(client, permit, location="Otro sitio")
        plan.refresh_from_db()

        assert plan.flight_permission_id == permit.pk
        assert not AuditEvent.objects.filter(
            action__in=(
                "geoplan_linked_to_permission",
                "geoplan_unlinked_from_permission",
            )
        ).exists()

    def test_a_plan_of_another_tenant_cannot_be_chosen(self, centers, tenants, author):
        permit = make_permit(centers["a"])
        foreign = make_plan(centers["b"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        response = self._post(client, permit, source_plan=str(foreign.pk))

        assert response.status_code == 200
        assert "source_plan" in response.context["form"].errors
        foreign.refresh_from_db()
        assert foreign.flight_permission_id is None

    def test_a_plan_of_another_cost_center_is_rejected(self, centers, tenants, author):
        permit = make_permit(centers["a"])
        other = make_plan(centers["a2"], author, circle_document())
        client = login_as(*FORM_PERMS, *LINK_PERMS, member_of=tenants[0])

        response = self._post(client, permit, source_plan=str(other.pk))

        assert response.status_code == 200
        assert "source_plan" in response.context["form"].errors

    def test_without_change_geoplan_the_chosen_plan_is_not_accepted(
        self, centers, tenants, author
    ):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as(*FORM_PERMS, "view_geoplan", member_of=tenants[0])

        response = self._post(client, permit, source_plan=str(plan.pk))

        assert response.status_code == 200
        plan.refresh_from_db()
        assert plan.flight_permission_id is None


# ── el modal «Subir un KMZ nuevo» ───────────────────────────────────────────


def kml_upload(document=None, name="plan.kml"):
    return SimpleUploadedFile(
        name,
        build_kml_bytes(document or circle_document()),
        content_type="application/vnd.google-earth.kml+xml",
    )


HTMX = {"HTTP_HX_REQUEST": "true", "HTTP_ACCEPT_LANGUAGE": "en"}


@pytest.mark.django_db
class TestTheImportModal:
    def test_it_is_the_import_view_answering_with_a_fragment(self, centers, tenants):
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.get(
            reverse("geo-plan-import"), {"cost_center": centers["a"].pk}, **HTMX
        )

        html = response.content.decode()
        assert response.status_code == 200
        assert "<html" not in html and "Upload a new KMZ" in html
        # La faena viene precargada y no se pregunta por un permiso que quizá no existe.
        assert f'<option value="{centers["a"].pk}" selected>' in html
        assert "flight_permission" not in html
        assert 'hx-post="' + reverse("geo-plan-import") + '"' in html

    def test_the_plain_page_is_still_the_full_page(self, centers, tenants):
        client = login_as("add_geoplan", member_of=tenants[0])
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"

        html = client.get(reverse("geo-plan-import")).content.decode()

        assert "<html" in html and "flight_permission" in html

    def test_it_needs_add_geoplan(self, centers, tenants):
        client = login_as("view_geoplan", "change_geoplan", member_of=tenants[0])

        assert client.get(reverse("geo-plan-import"), **HTMX).status_code == 403
        post = client.post(
            reverse("geo-plan-import"),
            {"cost_center": centers["a"].pk, "file": kml_upload()},
            **HTMX,
        )
        assert post.status_code == 403 and GeoPlan.objects.count() == 0

    def test_a_cost_center_of_another_tenant_is_404(self, centers, tenants):
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.get(
            reverse("geo-plan-import"), {"cost_center": centers["b"].pk}, **HTMX
        )

        assert response.status_code == 404

    def test_posting_a_cost_center_of_another_tenant_creates_nothing(
        self, centers, tenants, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.post(
            reverse("geo-plan-import"),
            {"cost_center": centers["b"].pk, "file": kml_upload()},
            **HTMX,
        )

        assert response.status_code == 422
        assert "cost_center" in response.context["form"].errors
        assert GeoPlan.objects.count() == 0

    def test_importing_creates_the_plan_as_a_draft_and_announces_it(
        self, centers, tenants, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.post(
            reverse("geo-plan-import"),
            {"cost_center": centers["a"].pk, "file": kml_upload()},
            **HTMX,
        )

        plan = GeoPlan.objects.get()
        assert response.status_code == 200
        # Decisión 2.1: el mismo estado que hoy la importación normal.
        assert plan.status == "draft" and plan.cost_center == centers["a"]
        assert plan.flight_permission_id is None
        assert plan.source_document is not None and plan.current_version is not None
        event = json.loads(response["HX-Trigger-After-Swap"])["geoplan-imported"]
        assert event == {
            "id": str(plan.pk),
            "label": f"{plan.folio} · {plan.title}",
            "areas": 1,
        }
        assert plan.folio in response.content.decode()

    def test_a_plan_of_several_areas_says_so_and_chooses_none(
        self, centers, tenants, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.post(
            reverse("geo-plan-import"),
            {
                "cost_center": centers["a"].pk,
                "file": kml_upload(two_circles_document()),
            },
            **HTMX,
        )

        assert (
            json.loads(response["HX-Trigger-After-Swap"])["geoplan-imported"]["areas"]
            == 2
        )
        assert (
            "2 areas: separate them into flight requests." in response.content.decode()
        )

    def test_a_bad_file_is_a_422_with_its_cause_and_creates_nothing(
        self, centers, tenants, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        client = login_as("add_geoplan", member_of=tenants[0])

        response = client.post(
            reverse("geo-plan-import"),
            {
                "cost_center": centers["a"].pk,
                "file": SimpleUploadedFile("plan.txt", b"no es un kml"),
            },
            **HTMX,
        )

        assert response.status_code == 422
        assert "Only .kml and .kmz files can be imported." in response.content.decode()
        assert GeoPlan.objects.count() == 0

    def test_the_new_plan_can_then_be_chosen_in_the_permit_form(
        self, centers, tenants, settings, tmp_path
    ):
        """El recorrido entero: importar en el modal y guardar el permiso con ese plan."""
        settings.DOCUMENTS_ROOT = str(tmp_path)
        client = login_as(*FORM_PERMS, *LINK_PERMS, "add_geoplan", member_of=tenants[0])
        client.post(
            reverse("geo-plan-import"),
            {"cost_center": centers["a"].pk, "file": kml_upload()},
            **HTMX,
        )
        plan = GeoPlan.objects.get()
        form = FlightPermissionForm(user=client.user)

        assert plan in set(form.fields["source_plan"].queryset)


# ── la ficha lee el plan vinculado ──────────────────────────────────────────


@pytest.mark.django_db
class TestTheFichaReadsTheLinkedPlan:
    def _linked(self, centers, author, document=None):
        permit = make_permit(centers["a"])
        plan = make_plan(centers["a"], author, document or circle_document())
        GeoPlan.objects.filter(pk=plan.pk).update(flight_permission=permit)
        return permit, plan

    def test_it_shows_the_reading_and_the_map_with_the_long_derived_notice(
        self, centers, tenants, author
    ):
        permit, plan = self._linked(centers, author)
        client = login_as("view_flightpermission", "view_geoplan", member_of=tenants[0])

        html = html_of(client, reverse("permission-detail", args=[permit.pk]))
        section = html.split('id="permit-location"')[1].split('id="permit-validity"')[0]

        assert 'id="permit-plan-reading"' in section
        assert (
            "What the KMZ brings" in section and f'id="mini-map-{plan.pk}"' in section
        )
        # En la ficha sí va el «¿Por qué?» de la BCN: es donde se confirma el dato.
        assert "come from the BCN administrative boundaries" in section
        assert "js/geo/mini-map.js" in html and "css/geo-mini-map.css" in html

    def test_without_view_geoplan_there_is_no_reading_and_no_map(
        self, centers, tenants, author
    ):
        permit, _plan = self._linked(centers, author)
        client = login_as("view_flightpermission", member_of=tenants[0])

        html = html_of(client, reverse("permission-detail", args=[permit.pk]))

        assert "permit-plan-reading" not in html and "mini-map" not in html

    def test_without_a_plan_there_is_no_map(self, centers, tenants):
        permit = make_permit(centers["a"])
        client = login_as("view_flightpermission", "view_geoplan", member_of=tenants[0])

        html = html_of(client, reverse("permission-detail", args=[permit.pk]))

        assert "permit-plan-reading" not in html and "js/geo/mini-map.js" not in html

    def test_a_plan_of_several_areas_points_to_the_split_from_the_ficha_too(
        self, centers, tenants, author
    ):
        permit, plan = self._linked(centers, author, two_circles_document())
        client = login_as(
            "view_flightpermission",
            "view_geoplan",
            "add_flightrequest",
            member_of=tenants[0],
        )

        html = html_of(client, reverse("permission-detail", args=[permit.pk]))

        assert "2 areas: separate them into flight requests." in html
        assert reverse("geo-plan-split", args=[plan.pk]) in html


@pytest.mark.django_db
class TestTheSplitViewIsScopedByTenant:
    """El enlace «separar en solicitudes» de la vista previa llega acá: no puede abrir un plan ajeno."""

    def test_a_plan_of_another_tenant_is_404(self, centers, tenants, author):
        foreign = make_plan(centers["b"], author, two_circles_document())
        client = login_as("add_flightrequest", member_of=tenants[0])

        assert (
            client.get(reverse("geo-plan-split", args=[foreign.pk])).status_code == 404
        )
        assert (
            client.post(reverse("geo-plan-split", args=[foreign.pk])).status_code == 404
        )

    def test_an_own_plan_still_opens(self, centers, tenants, author):
        plan = make_plan(centers["a"], author, two_circles_document())
        client = login_as("add_flightrequest", member_of=tenants[0])

        assert client.get(reverse("geo-plan-split", args=[plan.pk])).status_code == 200


@pytest.mark.django_db
def test_the_new_strings_speak_spanish(centers, tenants, author):
    """El guardián de i18n no lee los `blocktranslate`: se afirma que cada uno sale en español."""
    permit = make_permit(centers["a"])
    other = make_plan(centers["a2"], author, circle_document())
    client = login_as(*FORM_PERMS, *LINK_PERMS, "add_geoplan", member_of=tenants[0])
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"

    create = client.get(reverse("permission-create")).content.decode()
    edit = client.get(reverse("permission-update", args=[permit.pk])).content.decode()
    mismatch = client.get(
        reverse("permission-plan-preview"),
        {"plan": other.pk, "cost_center": centers["a"].pk},
    ).content.decode()
    modal = client.get(
        reverse("geo-plan-import"),
        {"cost_center": centers["a"].pk},
        HTTP_HX_REQUEST="true",
    ).content.decode()

    assert "Estas casillas vendrán del plan al guardar" in create
    assert "Subir un KMZ nuevo" in create and "Elegir el archivo KMZ" in create
    assert "Vincular un plan geoespacial" in edit
    assert "Ese plan pertenece al centro de costo CC-A2" in mismatch
    assert "Subir un KMZ nuevo" in modal


# ── el script del selector, en Node ─────────────────────────────────────────

NODE_SCRIPT = r"""
const fs = require('fs');
const source = fs.readFileSync('./static/js/permission-plan-picker.js', 'utf8');

function makeEnv(withSelect) {
  const errors = [], dispatched = [], listeners = {};
  const options = [];
  const select = { options, value: '', dispatched,
    appendChild(o) { options.push(o); },
    dispatchEvent(e) { dispatched.push(e.type + ':' + select.value); } };
  const document = {
    body: { addEventListener(n, f) { (listeners[n] = listeners[n] || []).push(f); } },
    querySelector: () => (withSelect ? select : null),
    createElement: () => ({}),
  };
  class Event { constructor(type) { this.type = type; } }
  const window = { console: { error: (...a) => errors.push(a.join(' ')) } };
  new Function('window', 'document', 'Event', source)(window, document, Event);
  return { errors, listeners, select, options, dispatched };
}

const out = {};
// 1. htmx pide con `source_plan`; la vista espera `plan`.
let env = makeEnv(true);
const params = new Map([['source_plan', 'abc'], ['cost_center', 'cc']]);
params['delete'] = params.delete.bind(params);
env.listeners['htmx:configRequest'][0]({ detail: { elt: { hasAttribute: n => n === 'data-plan-picker-select' }, parameters: params } });
out.renamed = { plan: params.get('plan'), old: params.has('source_plan'), cc: params.get('cost_center') };
// otro elemento que pide algo no se toca
const other = new Map([['source_plan', 'x']]);
env.listeners['htmx:configRequest'][0]({ detail: { elt: { hasAttribute: () => false }, parameters: other } });
out.untouched = other.has('source_plan') && !other.has('plan');
// el selector vacío manda plan vacío (la vista responde con la ayuda)
const empty = new Map([['source_plan', '']]);
env.listeners['htmx:configRequest'][0]({ detail: { elt: { hasAttribute: () => true }, parameters: empty } });
out.empty = empty.get('plan');

// 2. importado: se agrega, se elige y se avisa el cambio; no se duplica.
env = makeEnv(true);
env.listeners['geoplan-imported'][0]({ detail: { id: 'p1', label: 'PG-1 · Plan', areas: 1 } });
env.listeners['geoplan-imported'][0]({ detail: { id: 'p1', label: 'PG-1 · Plan', areas: 1 } });
out.imported = { options: env.options.map(o => o.value + '|' + o.textContent), value: env.select.value, dispatched: env.dispatched, errors: env.errors };

// 3. sin selector en la página: se dice, no se cae.
env = makeEnv(false);
env.listeners['geoplan-imported'][0]({ detail: { id: 'p1' } });
out.noSelect = env.errors;
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def node_run():
    if NODE is None:
        pytest.skip("Node no está instalado")
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_the_picker_renames_its_parameter_without_touching_other_requests(node_run):
    assert node_run["renamed"] == {"plan": "abc", "old": False, "cc": "cc"}
    assert node_run["untouched"] is True
    assert node_run["empty"] == ""


def test_an_imported_plan_is_added_once_selected_and_announced(node_run):
    imported = node_run["imported"]
    assert imported["options"] == ["p1|PG-1 · Plan"]
    assert imported["value"] == "p1" and imported["errors"] == []
    # Dos avisos de cambio (uno por evento): es lo que dispara la vista previa de htmx.
    assert imported["dispatched"] == ["change:p1", "change:p1"]


def test_a_page_without_the_selector_names_the_problem(node_run):
    assert node_run["noSelect"] == [
        "plan-picker: imported: no selector or no plan in the event"
    ]
