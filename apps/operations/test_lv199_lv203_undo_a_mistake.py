"""LV-199 y LV-203: dos operaciones que se podían equivocar y no tenían salida.

**LV-199 — desvincular un plan del permiso.** Textual: *"agregar un botón o algo
para desvincular cuando exista algún error o equivocación"*. La ficha ofrecía
vincular e importar y ninguna tenía inversa — la misma mitad que faltaba y que
`R10.2` corrigió del otro lado, cuando sólo se podía importar.

Lo que no es obvio y es la decisión de la fila: **la ubicación que el vínculo
escribió se queda en el permiso, y el mensaje lo dice**. Borrarla dejaría un
permiso aprobado sin coordenadas, que es peor que uno con la ubicación de un plan
que ya no está; conservarla en silencio dejaría un dato sin fuente. Se conserva y
se avisa — el mismo trato que `LV-166` le dio a la procedencia.

**LV-203 — archivar un plan desde el listado.** El usuario lo pidió para cuando
se equivoca al dibujar el polígono, y propuso una confirmación de escribir
"BORRAR". Al mirarlo, lo que faltaba era otra cosa: **archivar ya existía desde
`LV-135`**, con su permiso propio (`delete_geoplan`) y con una confirmación que
exige **motivo escrito** cuando el plan dejó rastro (`LV-178`) — un freno más
fuerte que teclear una palabra, porque dice *por qué*. Lo que no existía era la
forma de llegar: la columna de acciones del listado sólo ofrecía "Restaurar", o
sea la vuelta sin la ida.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.geo.models import GeoPlan, GeoPlanPermissionLink
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def permit(center):
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-199",
        cost_center=center,
        purpose="patrol",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=60),
        location="Quebrada km 13",
        area_type="unpopulated",
    )


def _plan(center, permit=None, title="CG-02_circunferencia_grande"):
    author, _created = User.objects.get_or_create(username="autor-199")
    return GeoPlan.objects.create(
        title=title,
        cost_center=center,
        created_by=author,
        flight_permission=permit,
    )


@pytest.mark.django_db
class TestUnlinkingAPlan:
    def test_it_clears_the_link(self, center, permit):
        plan = _plan(center, permit)

        response = login_as("view_flightpermission", "change_geoplan").post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        assert response.status_code == 302
        plan.refresh_from_db()
        assert plan.flight_permission is None

    def test_the_location_stays_on_the_permit(self, center, permit):
        """**La decisión de la fila.** Al vincular, el plan rellena la ubicación;
        al desvincular, esa ubicación se queda. Borrarla dejaría un permiso
        aprobado sin coordenadas — peor que tenerlas de un plan que ya no está."""
        permit.latitude = -24.25
        permit.longitude = -70.0
        permit.radius_km = 3.1
        permit.save(update_fields=["latitude", "longitude", "radius_km"])
        plan = _plan(center, permit)

        login_as("view_flightpermission", "change_geoplan").post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        permit.refresh_from_db()
        assert float(permit.latitude) == -24.25
        assert permit.radius_km is not None

    def test_the_unlink_is_on_record_without_writing_it_twice(self, center, permit):
        """`GeoPlanPermissionLink` (`OPS-7`) registra todo cambio de esa FK por sí
        solo, **incluido el paso a nulo**. Escribir además una bitácora propia
        serían dos versiones del mismo hecho."""
        plan = _plan(center, permit)

        login_as("view_flightpermission", "change_geoplan").post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        último = GeoPlanPermissionLink.objects.filter(plan=plan).order_by("-pk").first()
        assert último.previous_permission_id == permit.pk
        assert último.new_permission_id is None

    def test_a_plan_of_another_permit_is_refused(self, center, permit):
        """No es un error del sistema sino un formulario viejo o una URL armada a
        mano, y se responde diciéndolo — mismo criterio que al vincular."""
        otro = FlightPermission.objects.create(
            internal_folio="JEJ-2026-200",
            cost_center=center,
            purpose="patrol",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=60),
            location="Otra",
            area_type="unpopulated",
        )
        plan = _plan(center, otro)

        login_as("view_flightpermission", "change_geoplan").post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        plan.refresh_from_db()
        assert plan.flight_permission == otro

    def test_it_needs_the_permission_to_change_plans(self, center, permit):
        plan = _plan(center, permit)

        response = login_as("view_flightpermission").post(
            reverse("permission-unlink-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        assert response.status_code == 403
        plan.refresh_from_db()
        assert plan.flight_permission == permit

    def test_the_button_is_on_the_permit_page(self, center, permit):
        _plan(center, permit)

        content = (
            login_as("view_flightpermission", "view_geoplan", "change_geoplan")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert reverse("permission-unlink-plan", args=[permit.pk]) in content

    def test_without_the_permission_there_is_no_button(self, center, permit):
        """Ofrecer un botón que termina en 403 enseña a desconfiar de la pantalla
        — la regla que `LV-130` escribió para los atajos del expediente."""
        _plan(center, permit)

        content = (
            login_as("view_flightpermission", "view_geoplan")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert reverse("permission-unlink-plan", args=[permit.pk]) not in content


@pytest.mark.django_db
class TestArchivingFromTheList:
    def test_the_list_offers_it(self, center):
        plan = _plan(center)

        content = (
            login_as("view_geoplan", "delete_geoplan")
            .get(reverse("geo-plan-list"))
            .content.decode()
        )

        assert reverse("geo-plan-archive", args=[plan.pk]) in content

    def test_it_needs_the_delete_permission(self, center):
        """El "permiso especial" que el usuario pedía ya existía: `delete_geoplan`
        es la puerta de salida y la vista lo exige."""
        plan = _plan(center)

        content = (
            login_as("view_geoplan").get(reverse("geo-plan-list")).content.decode()
        )

        assert reverse("geo-plan-archive", args=[plan.pk]) not in content

    def test_a_plan_with_history_still_asks_for_a_written_reason(self, center, permit):
        """**Por qué no se agregó "escriba BORRAR"**: cuando el plan dejó rastro,
        archivar ya exige un motivo escrito (`LV-178`), que dice *por qué* y no
        sólo que alguien leyó. El POST desde el listado cae en esa misma pantalla
        de confirmación, así que la fila nueva no rodea el freno: lo reusa."""
        plan = _plan(center, permit)

        response = login_as("view_geoplan", "delete_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk])
        )

        assert response.status_code == 200  # la confirmación, no un 302
        plan.refresh_from_db()
        assert plan.is_active

    def test_the_round_trip_still_works(self, center):
        """La ida y la vuelta desde la misma columna, que es lo que `LV-135` dejó
        a medias: tenía la vuelta y le faltaba la ida."""
        plan = _plan(center)
        client = login_as("view_geoplan", "delete_geoplan", "change_geoplan")

        client.post(reverse("geo-plan-archive", args=[plan.pk]))
        plan.refresh_from_db()
        assert not plan.is_active

        client.post(reverse("geo-plan-restore", args=[plan.pk]))
        plan.refresh_from_db()
        assert plan.is_active
