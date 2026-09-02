"""R3 + UX-06: el informe mensual visible, y que se pueda imprimir.

Lo que estos tests protegen, por orden de gravedad:

1. **Que la pantalla no filtre.** Nombra faenas, su cobertura y su estado de
   habilitación; sin `view_reportrun` no se abre. Es el contrato de `AGENTS.md`
   para toda vista de lectura, y la lección de `LV-191`, donde un panel llevaba
   meses listando personas con su credencial por vencer porque el guard que lo
   tapaba no era un control de acceso.
2. **Que un informe congelado se dibuje desde su payload y no desde la base.**
   Es la razón de existir de `ReportRun`: el de agosto tiene que seguir diciendo
   en diciembre lo que decía en agosto.
3. **Que un hueco se vea como hueco.** Sin dato, ámbar punteado; nunca un cero.
"""

import re
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter
from apps.reporting.models import ReportRun
from apps.reporting.views import parse_period, previous_month

URL = "monthly-report"


@pytest.fixture
def reader(db):
    user = User.objects.create_user("reader", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    return user


@pytest.fixture
def outsider(db):
    return User.objects.create_user("outsider", password="x")


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


class TestTheScreenIsGated:
    @pytest.mark.django_db
    def test_a_user_without_the_permission_gets_403(self, client, outsider):
        """No basta con haber iniciado sesión.

        La página nombra cada faena y si está habilitada para volar; eso es
        información de cumplimiento, no un tablero público.
        """
        client.force_login(outsider)

        response = client.get(reverse(URL))

        assert response.status_code == 403

    @pytest.mark.django_db
    def test_anonymous_is_sent_to_the_login(self, client):
        response = client.get(reverse(URL))

        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    @pytest.mark.django_db
    def test_the_permission_opens_it(self, client, reader, site):
        client.force_login(reader)

        response = client.get(reverse(URL))

        assert response.status_code == 200


class TestThePeriod:
    def test_it_defaults_to_the_month_already_closed(self):
        """Abrir la pantalla el 2 de septiembre y encontrar septiembre a medio
        correr invita a leer como cierre lo que todavía se mueve."""
        assert previous_month(date(2026, 9, 2)) == date(2026, 8, 1)

    def test_january_falls_back_to_the_previous_year(self):
        assert previous_month(date(2026, 1, 14)) == date(2025, 12, 1)

    def test_a_period_in_the_query_wins(self):
        assert parse_period("2026-08", date(2026, 9, 2)) == date(2026, 8, 1)

    @pytest.mark.parametrize("raw", [None, "", "agosto", "2026", "2026-13", "26-8-x"])
    def test_a_broken_period_falls_back_instead_of_exploding(self, raw):
        """El parámetro llega de un `<input type="month">` y de enlaces pegados
        a mano. Un 500 por un mes mal escrito no le dice nada a nadie."""
        assert parse_period(raw, date(2026, 9, 2)) == date(2026, 8, 1)


class TestTheCoverFollowsThePeriod:
    """Pedido del usuario: *"revisar que la portada del informe va avanzando
    según el mes y el año que indique, y el día"*.

    Son **cinco** cosas que tienen que moverse juntas —el código del documento,
    la banda del mes, el rango de días, la fecha de corte y la cabecera que
    repiten las páginas 2 a 5—, y basta que una se quede fija para que el
    informe se contradiga a sí mismo. El caso que las separa es febrero: el día
    de corte no es una constante, es el último del mes que se pida.
    """

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("period", "band", "last_day"),
        [
            ("2026-08", "AGOSTO 2026", "31"),
            ("2026-09", "SEPTIEMBRE 2026", "30"),
            ("2025-12", "DICIEMBRE 2025", "31"),
            # Bisiesto y común, uno detrás del otro: si el día de corte
            # estuviera escrito en la plantilla, éstos dos serían iguales.
            ("2028-02", "FEBRERO 2028", "29"),
            ("2027-02", "FEBRERO 2027", "28"),
        ],
    )
    def test_every_dated_field_moves_with_it(
        self, client, reader, site, period, band, last_day
    ):
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": period}).content.decode()

        year, month = period.split("-")
        assert f"JEJ-GTE-CT-INF-RPA-{period}" in body
        assert band in body
        assert f"Período 01–{last_day} de" in body
        assert f"{last_day}-{month}-{year}" in body

    @pytest.mark.django_db
    def test_the_header_of_every_page_carries_the_same_period(
        self, client, reader, site
    ):
        """Las cinco hojas llevan el código arriba, y en el ZIP estaba escrito
        cuatro veces a mano. Cuatro copias de un código es cómo una página
        termina diciendo otro período que la portada."""
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": "2026-09"}).content.decode()

        # Se cuenta dentro de `rpt-head-code` y no en todo el cuerpo: el código
        # sale además en el `<title>` y en el encabezado de la pantalla, que no
        # son parte del documento — contar el cuerpo entero mediría el marco de
        # la aplicación y se rompería al tocarlo.
        headers = re.findall(r'class="rpt-head-code"[^>]*>\s*([A-Z0-9-]+)', body)

        assert headers == ["JEJ-GTE-CT-INF-RPA-2026-09"] * 5
        assert "JEJ-GTE-CT-INF-RPA-2026-08" not in body

    @pytest.mark.django_db
    def test_the_month_selector_shows_the_period_being_read(self, client, reader, site):
        """El campo tiene que decir qué se está mirando, o al pedir el mes
        siguiente se parte de la casilla vacía cada vez."""
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": "2025-12"}).content.decode()

        assert 'value="2025-12"' in body


class TestAFrozenReportComesFromItsPayload:
    @pytest.mark.django_db
    def test_the_stored_figures_are_drawn_not_recalculated(self, client, reader, site):
        """**La prueba de que congelar sirve para algo.**

        La base dice que hay un permiso vigente; el informe guardado dice 11.
        Si la pantalla dibujara 1, `ReportRun` sería decoración: un informe
        emitido cambiaría solo al cambiar la base, y con él desaparecería la
        evidencia de lo que se reportó.
        """
        today = date(2026, 8, 31)
        FlightPermission.objects.create(
            cost_center=site,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            location="Site",
            area_type="unpopulated",
            valid_from=today - timedelta(days=30),
            valid_until=today + timedelta(days=30),
        )
        ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="cron",
            payload={
                "meta": {
                    "code": "JEJ-GTE-CT-INF-RPA-2026-08",
                    "cutoff": "2026-08-31",
                    "covers": {"from": "2026-08-01", "to": "2026-08-31"},
                    "issued_by": "Gerente de Operaciones Aéreas ante la DGAC",
                    "jointly_with": "Jefe Seguridad Aérea ante la DGAC",
                    "standard": "JEJ-GRI-SS-INS-096 Rev. 0",
                    "addressed_to": "Gerencia General",
                    "scope": "Vigencia de permisos de vuelo ante la DGAC",
                    "sources": "AeroControl · SIGO — DGAC",
                },
                "kpis": {
                    "permits_in_force": {
                        "value": 11,
                        "source": "operations",
                        "cutoff": "2026-08-31",
                    }
                },
                "cost_centres": [],
            },
        )
        client.force_login(reader)

        response = client.get(reverse(URL), {"period": "2026-08"})
        body = response.content.decode()

        assert response.context["run"] is not None
        assert ">11<" in body

    @pytest.mark.django_db
    def test_without_a_frozen_run_it_says_so(self, client, reader, site):
        """Un borrador que alguien imprima y firme creyéndolo emitido es el peor
        resultado posible de esta pantalla, y en el papel los dos son idénticos.
        """
        client.force_login(reader)

        response = client.get(reverse(URL))

        assert response.context["run"] is None
        assert "alert-warning" in response.content.decode()


class TestAHoleLooksLikeAHole:
    @pytest.mark.django_db
    def test_a_missing_leaf_is_drawn_as_pending_and_never_as_zero(self, client, reader):
        """La regla que manda sobre todo el informe, comprobada en la pantalla.

        Un cero afirma ("hay cero") y la ausencia no afirma nada. Mezclarlas es
        cómo un informe firmado ante la autoridad declara cumplimiento sobre un
        hueco de carga.
        """
        ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="cron",
            payload={
                "meta": {"code": "X", "cutoff": "2026-08-31"},
                "kpis": {
                    "permits_in_force": {
                        "value": None,
                        "source": "operations",
                        "cutoff": "2026-08-31",
                    }
                },
                "cost_centres": [],
            },
            missing_fields=["kpis.permits_in_force"],
        )
        client.force_login(reader)

        response = client.get(reverse(URL), {"period": "2026-08"})
        body = response.content.decode()

        assert "rpt-pending" in body
        assert response.context["missing_fields"] == ["kpis.permits_in_force"]

    @pytest.mark.django_db
    def test_a_zero_is_drawn_as_a_zero(self, client, reader, site):
        """El otro lado de la misma moneda: cero **es** un dato.

        Sin faenas con permiso, la tarjeta dice 0 y no "pendiente" — la
        diferencia entre "se miró y no hay ninguno" y "no se sabe".
        """
        client.force_login(reader)

        response = client.get(reverse(URL))

        assert response.context["payload"]["kpis"]["permits_in_force"]["value"] == 0
        assert response.context["missing_fields"] == []


class TestTheCostCentreTableReadsTheRightWay:
    @pytest.mark.django_db
    def test_a_site_without_permits_is_listed_as_unlicensed(self, client, reader, site):
        """La página existe para mostrar las faenas que **no** pueden volar.

        `permit_status_by_cost_center` parte de las faenas y no de los permisos
        justamente por esto (`LV-206`): con el recorrido al revés esta fila no
        existiría y la tabla contestaría lo contrario de la pregunta.
        """
        client.force_login(reader)

        body = client.get(reverse(URL)).content.decode()

        assert "CC738" in body
        assert "Sin habilitación" in body


class TestTheStampAndThePrintRules:
    @pytest.mark.django_db
    def test_the_generation_stamp_is_rendered(self, client, reader, site):
        """UX-06: un papel sin fecha de generación no se contrasta con nada."""
        client.force_login(reader)

        body = client.get(reverse(URL)).content.decode()

        assert "print-stamp" in body
        assert "reader" in body

    def test_the_app_stylesheet_has_print_rules(self):
        """El árbol tenía **cero** `@media print`: toda impresión salía con la
        navegación encima. Se afirma sobre el archivo porque es donde vive la
        regla, y un test que abriera un navegador mediría otra cosa."""
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        assert "@media print" in css
        assert ".print-stamp" in css

    def test_the_report_sheet_prints_one_page_per_sheet(self):
        """Cada hoja del informe **es** una página A4.

        El diseño posiciona el pie en absoluto contra los 1123 px, así que una
        hoja repartida entre dos páginas deja el pie en medio de la segunda.
        """
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "report-a4.css").read_text(
            encoding="utf-8"
        )

        assert "@page { size: A4; margin: 0; }" in css
        assert "break-inside: avoid" in css
