"""LV-246: lo vencido se ve, y se ve como crítico.

Tres pedidos del usuario del 2026-09-23, con capturas de producción, que son la
misma idea:

1. *"Ubicar en el dashboard los centros de costo con incumplimiento sin permisos
   vigentes, que es crítico; según el avance del plan se le exige mínimo tener el
   permiso de vuelo."*
2. *"Mostrar también cuando el permiso que se cruza con el geoespacial está
   vencido."*
3. *"Mejorar la distribución de la tabla, algunas letras apretadas; cuando un
   permiso vencido o caducado, que sea marcado en ROJO con alguna marca."*

⚠️ **Y un hallazgo que cambia cómo leer el primero**: la fila sin permiso de la
tabla del panel escribía `class="table-warning-subtle"` desde `LV-206`, y esa clase
**no existe** ni en `app.css` ni en Bootstrap. La fila que el comentario decía
destacar nunca se pintó de nada; el guardián de abajo impide que se repita.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


def _permit(centre, status, valid_until, valid_from=None):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        location="Sector",
        area_type="unpopulated",
        valid_from=valid_from or valid_until - timedelta(days=60),
        valid_until=valid_until,
    )


def _centre(code):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _operation():
    """Una aeronave activa, para que el panel sea el panel.

    Sin flota, padrón, alertas ni vencimientos el panel dibuja «Comienza tu
    operación» en lugar de todo lo demás (`show_onboarding`, `LV-187`), y la tabla y
    la tarjeta que estos tests buscan no existen en el HTML. El contexto sí las trae,
    y por eso los tests que leen el contexto pasaban y éstos no: es la trampa que
    `test_lv186` ya dejó escrita.
    """
    from apps.registry.models import Aircraft

    Aircraft.objects.create(
        registration="RPA-0001",
        type="RPA",
        model="M3",
        manufacturer="DJI",
        status="active",
    )


class TestSitesWithoutAPermitComeFirst:
    @pytest.mark.django_db
    def test_they_lead_the_table(self, client, admin_user):
        """Estaban ordenadas por código y repartidas entre las que sí tienen: en
        producción son siete de quince, y había que recorrer la tabla entera."""
        covered = _centre("CC100")
        _permit(covered, FlightPermission.STATUS_APPROVED, TODAY + timedelta(days=40))
        _centre("CC900")
        client.force_login(admin_user)

        rows = client.get(reverse("dashboard")).context["permit_status_rows"]

        assert [row["cost_center"].code for row in rows] == ["CC900", "CC100"]

    @pytest.mark.django_db
    def test_the_card_counts_them(self, client, admin_user):
        """Es el numerador del indicador que el informe firma como
        `cost_centres_without_permit`, que hasta hoy sólo existía en el papel."""
        covered = _centre("CC100")
        _permit(covered, FlightPermission.STATUS_APPROVED, TODAY + timedelta(days=40))
        _centre("CC900")
        _centre("CC901")
        _operation()
        client.force_login(admin_user)

        response = client.get(reverse("dashboard"))

        assert response.context["cost_centres_without_permit"] == 2
        assert "Faenas sin permiso" in response.content.decode()

    @pytest.mark.django_db
    def test_the_report_keeps_its_own_order(self, db):
        """⚠️ Se ordena en la vista del panel y **no** en el selector, porque el
        informe mensual lo comparte y allá la tabla va por código: es un documento
        formal que alguien coteja fila por fila. El cálculo es uno; el orden, no."""
        from apps.compliance.kpis import permit_status_by_cost_center

        covered = _centre("CC100")
        _permit(covered, FlightPermission.STATUS_APPROVED, TODAY + timedelta(days=40))
        _centre("CC900")

        codes = [row["cost_center"].code for row in permit_status_by_cost_center(TODAY)]

        assert codes == ["CC100", "CC900"]

    @pytest.mark.django_db
    def test_their_row_carries_the_critical_class(self, client, admin_user):
        _centre("CC900")
        _operation()
        client.force_login(admin_user)

        content = client.get(reverse("dashboard")).content.decode()

        assert 'class="row-critical"' in content


class TestNoMoreGhostClasses:
    def test_the_critical_row_class_exists_in_the_stylesheet(self):
        """El guardián. `table-warning-subtle` se escribió, se revisó y se desplegó
        sin existir, y nadie lo notó en quince meses porque una clase desconocida no
        falla: simplemente no pinta. Comprobarlo contra el archivo es lo único que lo
        detecta."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        assert re.search(r"tr\.row-critical\s*>\s*td\s*\{", css)

    def test_the_class_that_never_existed_is_gone(self):
        template = (
            Path(settings.BASE_DIR) / "templates" / "dashboard" / "index.html"
        ).read_text(encoding="utf-8")

        assert 'class="table-warning-subtle"' not in template


class TestALapsedPermitSaysSo:
    @pytest.mark.django_db
    def test_expired_is_lapsed(self, db):
        permit = _permit(
            _centre("CC100"), FlightPermission.STATUS_EXPIRED, TODAY - timedelta(days=4)
        )

        assert permit.has_lapsed

    @pytest.mark.django_db
    def test_approved_with_a_past_date_is_lapsed_before_the_nightly_job(self, db):
        """La mitad que mirar el estado no ve: entre medianoche y la corrida de
        `expire_permissions`, el permiso vencido sigue diciendo "Aprobado"."""
        permit = _permit(
            _centre("CC100"),
            FlightPermission.STATUS_APPROVED,
            TODAY - timedelta(days=1),
        )

        assert permit.has_lapsed

    @pytest.mark.django_db
    def test_approved_and_in_force_is_not(self, db):
        permit = _permit(
            _centre("CC100"),
            FlightPermission.STATUS_APPROVED,
            TODAY + timedelta(days=5),
        )

        assert not permit.has_lapsed

    @pytest.mark.django_db
    def test_denied_never_had_a_validity_to_lose(self, db):
        permit = _permit(
            _centre("CC100"), FlightPermission.STATUS_DENIED, TODAY - timedelta(days=4)
        )

        assert not permit.has_lapsed

    @pytest.mark.django_db
    def test_the_list_paints_it_red_with_a_mark(self, client, admin_user):
        """Caía en `bg-warning`, el mismo ámbar que «Solicitado»."""
        _permit(
            _centre("CC100"), FlightPermission.STATUS_EXPIRED, TODAY - timedelta(days=4)
        )
        client.force_login(admin_user)

        content = client.get(reverse("permission-list")).content.decode()

        assert '<span class="badge sev-critical">⚠ Caducado</span>' in content

    @pytest.mark.django_db
    def test_the_fiche_says_the_same_as_the_list(self, client, admin_user):
        permit = _permit(
            _centre("CC100"),
            FlightPermission.STATUS_APPROVED,
            TODAY - timedelta(days=1),
        )
        client.force_login(admin_user)

        content = client.get(permit.get_absolute_url()).content.decode()

        assert "⚠ Caducado" in content


class TestTheEmptyRowMatchesTheColumns:
    def test_the_permit_list_empty_row_spans_exactly_its_columns(self):
        """Ahora que la lista es `table-normalized`, un `colspan` mayor que sus
        `<col>` crea columnas inexistentes y les reparte el ancho de la flexible —
        medido en operadores: de 424 px a 5. `test_ux07_worktable` lo vigila en
        general; éste fija el número de esta lista."""
        base = Path(settings.BASE_DIR) / "templates" / "operations"
        cols = (
            (base / "permission_list.html").read_text(encoding="utf-8").count("<col ")
        )
        rows = (base / "_permission_rows.html").read_text(encoding="utf-8")

        assert f'colspan="{cols}"' in rows
        assert 'colspan="99"' not in rows
