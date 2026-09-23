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

from apps.core.testing import without_template_comments
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

    ⚠️ **`LV-233` separó la fecha de corte de las otras cuatro, y hay que saber
    por qué**: las otras cuatro describen **lo que el informe cubre** —el mes
    entero, haya terminado o no— y el corte describe **hasta dónde miró**. Son la
    misma cosa sólo cuando el mes ya cerró. Mientras estaban juntas, la portada de
    un mes en curso fechaba su corte en el futuro. Los dos casos tienen ahora su
    test propio, abajo.
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

        assert f"JEJ-GTE-CT-INF-RPA-{period}" in body
        assert band in body
        # Lo que el informe **cubre** sigue siendo el mes entero, haya terminado
        # o no: eso es el período, no el corte.
        assert f"Período 01–{last_day} de" in body

    @pytest.mark.django_db
    def test_a_closed_month_is_cut_at_its_last_day(self, client, reader, site):
        """La regla de siempre, para el caso que el informe describe: un mes
        cerrado se corta el día que cerró, y no "hoy" — usar hoy haría que el
        mismo período diera cifras distintas según cuándo se generara."""
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": "2026-08"}).content.decode()

        assert "31-08-2026" in body
        assert "período en curso" not in body

    @pytest.mark.django_db
    def test_an_unfinished_month_is_cut_today_and_says_so(
        self, client, reader, site, monkeypatch
    ):
        """⚠️ **Este es el test que `LV-233` mandaba cambiar, y se cambia a
        propósito.**

        Antes esta clase afirmaba que el corte es el último día del mes **para
        cualquier período**, incluidos los que no han terminado. El usuario lo vio
        en pantalla el 2026-09-03: la portada de septiembre, abierta el día 3,
        declaraba *"FECHA DE CORTE 30-09-2026"* — una fecha que no había ocurrido,
        sobre datos que eran los de ese día.

        Lo que se conserva es **la condición**, no la afirmación: la portada sigue
        moviéndose con el período. Lo que cambia es que ya no puede fechar el
        corte en el futuro, y que cuando el período sigue abierto **lo dice en el
        papel**, que es donde tiene que constar porque esta hoja se firma.
        """
        from apps.core.testing import pin_today_mid_month

        today = pin_today_mid_month(monkeypatch)
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": f"{today:%Y-%m}"}).content.decode()

        assert f"{today:%d-%m-%Y}" in body
        assert "período en curso" in body

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


class TestTheFooterIsTheSameOnEveryPage:
    """El pie estaba escrito cinco veces y no coincidía consigo mismo: la
    portada anclada 16 px más arriba que las demás, con otra regla y otro
    rótulo, y sólo ella declaraba la revisión.

    Importa porque el informe **circula en papel**: alguien imprime la página 3
    para adjuntarla a un permiso, y esa hoja suelta tiene que decir de qué
    revisión salió y si el juego venía completo.
    """

    @pytest.mark.django_db
    def test_every_page_declares_its_number_and_the_total(self, client, reader, site):
        client.force_login(reader)

        body = client.get(reverse(URL)).content.decode()

        labels = [
            " ".join(match.split())
            for match in re.findall(
                r'class="rpt-foot-id"[^>]*>(.*?)</div>', body, re.DOTALL
            )
        ]

        # ⚠️ Contra `len(labels)` y no contra un 5 escrito: desde el 2026-09-08 la
        # sección de permisos pide tantas hojas como necesite, así que el total
        # es variable. El test anterior afirmaba «de 5» y habría empezado a
        # fallar por la razón correcta con el arreglo puesto — pero también
        # habría dejado pasar un pie que numera mal si el documento volviera a
        # tener cinco hojas por casualidad.
        assert len(labels) >= 5
        for number, label in enumerate(labels, start=1):
            assert f"Página {number} de {len(labels)}" in label

    @pytest.mark.django_db
    def test_every_page_declares_the_revision(self, client, reader, site):
        """Sin congelar es «Borrador», y decirlo también es declarar la
        revisión: lo que no puede pasar es que una hoja no diga nada."""
        client.force_login(reader)

        body = client.get(reverse(URL)).content.decode()

        assert body.count("Borrador ·") == 5

    def test_the_footer_takes_the_total_and_does_not_hardcode_it(self):
        """⚠️ Este test antes comprobaba lo contrario: que `_foot.html` escribiera
        «de 5» literal, con la premisa de que el juego es de cinco hojas «por
        estructura del documento». Era cierto para el informe emitido de agosto y
        falso desde que se midió que la tabla de permisos desborda la hoja — un
        total fijo convierte al pie en el que miente sobre cuántas hojas son, y
        es el dato con el que alguien comprueba que no le falta una página del
        juego impreso.

        Queda dado vuelta: lo que no se puede volver a escribir es el número."""
        from pathlib import Path

        from django.conf import settings

        foot = (
            Path(settings.BASE_DIR) / "templates" / "reporting" / "_foot.html"
        ).read_text(encoding="utf-8")

        assert "de {{ pages }}" in foot
        assert "de 5" not in without_template_comments(foot)

    def test_no_page_pins_its_own_number(self):
        """La numeración la asigna `MonthlyReportView._sheets`, en un solo lugar.
        Dos sitios decidiéndola es cómo un documento termina con dos hojas
        numeradas igual — y con la sección de permisos variable, un `page=4`
        escrito en la plantilla de cobertura empieza a mentir en cuanto entra un
        permiso más."""
        from pathlib import Path

        from django.conf import settings

        templates = Path(settings.BASE_DIR) / "templates" / "reporting"
        for page in sorted(templates.glob("_page*.html")):
            source = without_template_comments(page.read_text(encoding="utf-8"))
            assert not re.search(r"_foot\.html\" with page=\d", source), page.name

    def test_the_long_note_cannot_squeeze_the_page_label(self):
        """⚠️ El traslape. Los dos lados eran `<span>` sueltos en un flex sin
        base declarada: la nota de la página 3 —más de doscientos caracteres— se
        quedaba con el ancho y el rótulo se partía en dos renglones metidos bajo
        ella, empujando además la regla contra la tabla.

        Se afirma sobre el CSS porque es donde vive el reparto; medirlo en un
        navegador mediría la tipografía del que corra el test.
        """
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "report-a4.css").read_text(
            encoding="utf-8"
        )

        assert ".rpt-foot-note { flex: 1 1 auto; min-width: 0; }" in css
        # `flex: none` y sin quiebre: el rótulo pide su ancho y no lo cede.
        assert re.search(
            r"\.rpt-foot-id\s*{[^}]*flex:\s*none;[^}]*white-space:\s*nowrap;", css
        )

    def test_no_page_draws_its_own_footer_anymore(self):
        """La regla que mantiene lo anterior cierto: cinco copias vuelven a
        divergir en cuanto una se toca sola."""
        from pathlib import Path

        from django.conf import settings

        templates = Path(settings.BASE_DIR) / "templates" / "reporting"
        for page in sorted(templates.glob("_page*.html")):
            source = page.read_text(encoding="utf-8")
            assert '{% include "reporting/_foot.html"' in source, page.name
            assert 'class="rpt-foot"' not in source, page.name


class TestTheDocumentSaysWhatAPersonWrote:
    """Pedido del usuario el 2026-09-08: *"una mejor forma de editar y revisar el
    informe completo, lo que se modifica y los cambios más claro"*.

    Casi todo el informe se calcula del corte y **tres bloques** los redacta
    quien firma —la observación del período, los hallazgos y las acciones—, y los
    tres se veían igual que una cifra consultada. Quien revisaba no tenía forma
    de saber, mirando el documento, dónde podía intervenir.
    """

    @pytest.fixture
    def editable(self, db, site):
        user = User.objects.create_user("writer", password="x")
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_reportrun", "change_reportrun"],
                content_type__app_label="reporting",
            )
        )
        run = ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="test",
            status=ReportRun.STATUS_DRAFT,
            payload={"meta": {}, "kpis": {}, "permits": [], "cost_centres": []},
            period_note="La renovación de CC738 arrancó el 12.",
            findings=[
                {"severity": "warning", "title": "Renovación", "text": "Va tarde."}
            ],
        )
        return user, run

    @pytest.mark.django_db
    def test_the_written_blocks_carry_their_mark(self, client, editable):
        user, _run = editable
        client.force_login(user)

        body = client.get(reverse(URL), {"period": "2026-08"}).content.decode()

        # Dos bloques escritos en este informe: la observación y los hallazgos.
        assert body.count("rpt-written") == 2

    @pytest.mark.django_db
    def test_the_mark_links_to_the_form_that_edits_it(self, client, editable):
        """Decirle a alguien que un bloque es editable y dejarlo buscando dónde
        es la mitad de un aviso — el mismo criterio que los hallazgos de
        «¿Puedo volar?»."""
        user, run = editable
        client.force_login(user)

        body = client.get(reverse(URL), {"period": "2026-08"}).content.decode()

        assert reverse("monthly-report-narrative", args=[run.pk]) in body

    @pytest.mark.django_db
    def test_an_approved_report_shows_no_mark(self, client, editable):
        """Un informe aprobado no se toca: se emite una revisión. El enlace
        llevaría a un formulario que rechaza, y `LV-130` ya dejó escrito lo que
        eso enseña — a desconfiar de la pantalla."""
        user, run = editable
        ReportRun.objects.filter(pk=run.pk).update(status=ReportRun.STATUS_APPROVED)
        client.force_login(user)

        body = client.get(reverse(URL), {"period": "2026-08"}).content.decode()

        assert "rpt-written" not in body

    @pytest.mark.django_db
    def test_without_the_write_permission_there_is_no_mark(self, client, reader, site):
        """Quien sólo lee no gana un enlace que va a terminar en 403."""
        ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="test",
            status=ReportRun.STATUS_DRAFT,
            payload={"meta": {}, "kpis": {}, "permits": [], "cost_centres": []},
            period_note="Algo escrito.",
        )
        client.force_login(reader)

        body = client.get(reverse(URL), {"period": "2026-08"}).content.decode()

        assert "rpt-written" not in body

    def test_the_mark_never_reaches_the_paper(self):
        """⚠️ Lo más importante de esta fila. El informe sale **firmado** hacia la
        DGAC: un rótulo de «editable» sobre el documento entregado afirmaría algo
        falso —que el lector puede cambiarlo— y ensuciaría un papel controlado.

        La regla va en `report-a4.css` y no sólo en `app.css` porque esta hoja se
        imprime sola y no puede depender de que la otra esté cargada."""
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "report-a4.css").read_text(
            encoding="utf-8"
        )
        printing = css.split("@media print", 1)[1]

        assert ".rpt-written" in printing
        assert "display: none !important" in printing
