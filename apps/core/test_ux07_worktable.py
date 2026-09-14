"""UX-07: la tabla de trabajo, una sola vez.

El componente reemplaza el `<table>` escrito a mano en cada lista. Su criterio,
textual del plan: *"las 26 listas lo usan; ninguna pierde función; la suite sigue
verde"*. Estos tests fijan las dos mitades que no se ven en la suite existente:
que las listas migradas **ganaron** lo que el componente trae, y que el orden por
columna no es una puerta abierta al `order_by`.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.testing import login_as, without_template_comments

TEMPLATES = Path(settings.BASE_DIR) / "templates"

# Las ocho listas que se escribían la cáscara a mano. `task_list.html` no está, y
# la razón va en su propio test más abajo.
MIGRATED = [
    "compliance/alert_list.html",
    "compliance/deliverable_list.html",
    "compliance/document_list.html",
    "compliance/nonconformity_list.html",
    "geo/plan_list.html",
    "registry/battery_list.html",
    "registry/resourcemovementlog_list.html",
]


class TestEveryListGoesThroughTheComponent:
    @pytest.mark.parametrize("name", MIGRATED)
    def test_it_extends_the_worktable(self, name):
        content = (TEMPLATES / name).read_text(encoding="utf-8")

        assert '{% extends "generic/worktable.html" %}' in content

    @pytest.mark.parametrize("name", MIGRATED)
    def test_it_no_longer_writes_its_own_table(self, name):
        """La prueba de que la cáscara se comparte de verdad.

        Sin esto, una plantilla podría extender el componente y seguir dibujando
        su propia `<table>` adentro: el `extends` pasaría y la duplicación
        seguiría ahí, que es exactamente lo que esta fila vino a sacar.
        """
        # Los `{% comment %}` se recortan: un comentario no se renderiza, así que
        # nombrar `<table>` al explicar por qué una lista se dibuja como se
        # dibuja no es escribirse una tabla. Pasó apenas se documentó la reversión
        # de `LV-146` en `alert_list.html`, y es el mismo tropiezo que ya habían
        # tenido el guardián de traducciones y el de `scope` — por eso el recorte
        # vive en `apps.core.testing` y no copiado acá.
        content = without_template_comments(
            (TEMPLATES / name).read_text(encoding="utf-8")
        )

        assert "<table" not in content
        assert "table-responsive" not in content

    def test_the_generic_list_also_extends_it(self):
        """Las nueve que ya usaban `generic/list.html` entran por la misma
        puerta, o serían dos cáscaras conviviendo -- que es el problema con un
        archivo más."""
        content = (TEMPLATES / "generic" / "list.html").read_text(encoding="utf-8")

        assert '{% extends "generic/worktable.html" %}' in content
        assert "<table" not in content


class TestTheMigratedListsGainedWhatTheyLacked:
    """`ninguna pierde función` es la mitad fácil de verificar; que **ganen** la
    del componente es la que dice si valió la pena."""

    @pytest.mark.django_db
    def test_the_alert_list_now_has_the_bulk_bar(self, db):
        """Sus filas llevaban `data-pk` desde `UX-11`, así que `worktable.js`
        estaba listo para inyectar las casillas -- y no aparecía ninguna, porque
        la barra que las gobierna vivía sólo en `generic/list.html`."""
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert 'id="bulk-bar"' in body
        assert 'id="bulk-export"' in body

    @pytest.mark.django_db
    def test_the_plan_list_now_has_the_htmx_targets(self, db):
        """`GeoPlanList` declaraba `htmx_template_name` y su plantilla no tenía
        ni `#table-body` ni `#pagination-container`: la respuesta parcial no
        tenía dónde entrar."""
        client = login_as("view_geoplan")

        body = client.get(reverse("geo-plan-list")).content.decode()

        assert 'id="table-body"' in body
        assert 'id="pagination-container"' in body


class TestSortingIsAnAllowListAndNotAPassthrough:
    """`?sort=` viene de la URL y termina en `order_by`.

    Dejarla pasar sin filtrar permitiría ordenar por una tabla relacionada que
    nadie quiso exponer, y ordenar **es** un oráculo de lectura: la secuencia
    resultante habla de valores que no se mostraron.
    """

    @pytest.mark.django_db
    def test_an_unknown_column_is_ignored_not_an_error(self, db):
        """Un marcador viejo tiene que dibujar la lista, no una página de error."""
        client = login_as("view_alert")

        response = client.get(reverse("alert-list"), {"sort": "alert_rule__tenant__id"})

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_a_declared_column_actually_orders(self, db):
        from apps.registry.models import Battery

        Battery.objects.create(serial_number="B-002", cycle_count=10)
        Battery.objects.create(serial_number="B-001", cycle_count=99)
        client = login_as("view_battery")

        body = client.get(reverse("battery-list"), {"sort": "cycles"}).content.decode()
        rows = re.findall(r"B-00\d", body)

        # Menos ciclos primero: el orden pedido, no el de `Meta.ordering`
        # (`serial_number`), que habría puesto B-001 arriba.
        assert rows[:2] == ["B-002", "B-001"]

    @pytest.mark.django_db
    def test_the_direction_flips(self, db):
        from apps.registry.models import Battery

        Battery.objects.create(serial_number="B-002", cycle_count=10)
        Battery.objects.create(serial_number="B-001", cycle_count=99)
        client = login_as("view_battery")

        body = client.get(
            reverse("battery-list"), {"sort": "cycles", "dir": "desc"}
        ).content.decode()
        rows = re.findall(r"B-00\d", body)

        assert rows[:2] == ["B-001", "B-002"]

    @pytest.mark.django_db
    def test_sorting_keeps_the_filter_that_was_applied(self, db):
        """El enlace del encabezado lleva el resto de la query intacta. Sin eso,
        ordenar descartaría el filtro que la persona acaba de poner -- y se
        leería como que ordenar "no funciona"."""
        client = login_as("view_battery")

        body = client.get(reverse("battery-list"), {"q": "B-00"}).content.decode()

        assert "q=B-00&amp;sort=cycles" in body or "q=B-00&sort=cycles" in body

    @pytest.mark.django_db
    def test_sorting_returns_to_the_first_page(self, db):
        """La página 3 de otro orden es un lugar que nadie pidió.

        Se afirma primero que **hay** enlaces de orden y después que ninguno
        arrastra la página: sin la primera mitad, este test pasaría solo por no
        existir el componente, que es el defecto que vino a fijar.
        """
        client = login_as("view_battery")

        body = client.get(reverse("battery-list"), {"page": "1"}).content.decode()
        links = re.findall(r'href="(\?[^"]*sort=[^"]*)"', body)

        assert links, "el encabezado no dibujó ningún enlace de orden"
        assert not [link for link in links if "page=" in link]


class TestAHeaderWithoutAColumnStaysPlain:
    @pytest.mark.django_db
    def test_a_column_the_view_did_not_declare_draws_no_link(self, db):
        """Degradar a `<th>` a secas, en vez de un enlace que no hace nada.

        Es lo que deja migrar las 26 listas sin declarar 26 listas blancas el
        mismo día: la que todavía no declaró nada se ve exactamente como antes.
        """
        client = login_as("view_alert")

        from django.utils.translation import gettext

        body = client.get(reverse("alert-list")).content.decode()
        head = body.split("</thead>")[0]

        # El rótulo se pide al catálogo y no se escribe en español: escribirlo a
        # mano es la trampa de `LV-95`, que pasa en aislado y falla en la suite
        # completa según qué idioma dejó activo otro test.
        entity = gettext("Entity")
        assert entity in head
        # "Entidad" es una relación genérica: la vista no la declara, así que su
        # encabezado no puede ser un enlace de orden. Y el resto del encabezado
        # sí los tiene, o este test no estaría distinguiendo nada.
        assert "worktable-sort" not in head.split(entity)[1].split("</th>")[0]
        assert "worktable-sort" in head


class TestTheWorkboardListStaysOut:
    """`task_list.html` **no** se migra, y las tres razones son de fondo.

    (1) El tablero se da de baja por decisión del usuario (2026-08-12, ver
    `LV-78`): migrar una pantalla que se va es trabajo que se tira.

    (2) **Ya usa `?sort=` con otra semántica** -- un selector con `due`,
    `priority`, `assignee` y `progress`. El componente lee ese mismo parámetro,
    así que migrarla haría que dos mecanismos se pisen sobre la misma llave, y el
    que perdiera fallaría en silencio.

    (3) Su tabla no tiene la forma de una tabla de trabajo: filas de
    agrupamiento, un `offcanvas` de detalle y `container-fluid`.

    El test fija (2), que es la única que puede cambiar sin que nadie se entere.
    """

    def test_its_sort_parameter_would_collide(self):
        content = (TEMPLATES / "workboard" / "task_list.html").read_text(
            encoding="utf-8"
        )

        assert 'name="sort"' in content
        assert '{% extends "generic/worktable.html" %}' not in content


def _normalized_lists():
    """Las listas de ancho fijo, con su plantilla de filas, leídas del árbol.

    Se descubren en vez de enumerarse: una lista que se normalice mañana entra
    sola al guardián de abajo, que es justo el caso en que este defecto vuelve.
    """
    found = {}
    for page in sorted(TEMPLATES.glob("*/*_list.html")):
        source = page.read_text(encoding="utf-8")
        if "table-normalized" not in source:
            continue
        rows = re.search(r'{% include "([^"]+_rows\.html)" %}', source)
        if rows:
            found[page] = TEMPLATES / rows.group(1)
    return found


class TestTheEmptyRowSpansExactlyTheColumnsThereAre:
    """⚠️ **El defecto que el usuario encontró el 2026-09-11 buscando un operador
    que no existe.**

    La fila de «sin resultados» llevaba `colspan="99"` — el truco habitual para
    «que abarque todo», inofensivo en una tabla de reparto automático. En una
    `table-normalized` no lo es: el navegador **crea las columnas que el
    `colspan` promete** y reparte entre todas ellas el sobrante que le tocaba a
    `col-flex`.

    Medido en la lista de operadores: «Habilitaciones» pasaba de **424 px a 5**,
    y el encabezado de 56 px a **280**, con cada letra de la palabra en su propia
    línea. Cada columna inventada le roba la mitad a la flexible — con 8 daba
    212, con 99 daba 5.

    El número exacto vive en la plantilla de filas y los `<col>` en la de la
    lista: dos archivos distintos, así que la única forma de que no se separen es
    cruzarlos acá.
    """

    def test_the_tree_still_has_normalized_lists_to_check(self):
        """Si el descubrimiento deja de encontrar nada, los tests de abajo pasan
        sin comprobar nada — que es la forma en que un guardián se apaga solo."""
        assert len(_normalized_lists()) >= 4

    def test_the_colspan_matches_the_colgroup(self):
        for page, rows in _normalized_lists().items():
            columns = len(
                re.findall(
                    r"<col\s", without_template_comments(page.read_text("utf-8"))
                )
            )
            spans = [
                int(value)
                for value in re.findall(
                    r'colspan="(\d+)"',
                    without_template_comments(rows.read_text("utf-8")),
                )
            ]

            assert spans, f"{rows.name}: sin fila vacía que comprobar"
            for span in spans:
                assert span == columns, (
                    f"{rows.name} abarca {span} columnas y "
                    f"{page.name} declara {columns}"
                )

    def test_no_normalized_list_uses_the_catch_all_span(self):
        """El 99 es el que rompía. Se prohíbe por nombre para que el mensaje de
        error diga qué pasó, en vez de sólo que dos números no coinciden."""
        for _page, rows in _normalized_lists().items():
            source = without_template_comments(rows.read_text("utf-8"))

            assert 'colspan="99"' not in source, rows.name

    @pytest.mark.django_db
    def test_a_search_that_finds_nothing_offers_the_way_back(self):
        """`UX-18` en las cuatro listas del padrón, que se habían quedado atrás.

        Los dos vacíos no son el mismo hecho: sin filtros el padrón está vacío y
        lo que corresponde es ofrecer crear el primero; con un filtro puesto
        puede haber mucho y este recorte no alcanzarlo, así que lo que
        corresponde es ofrecer quitarlo. Las cuatro decían *"No se encontraron
        registros."* en los dos casos — el usuario lo vio el 2026-09-11 buscando
        un operador que no existe: la pantalla no le ofrecía volver.
        """
        from django.utils.translation import gettext

        client = login_as("view_operator")

        body = client.get(reverse("operator-list"), {"q": "zzzz"}).content.decode()

        assert gettext("No records match the current filters.") in body
        assert gettext("Clear filters") in body

    def test_every_normalized_list_makes_the_distinction(self):
        for _page, rows in _normalized_lists().items():
            source = without_template_comments(rows.read_text("utf-8"))

            assert "is_filtered" in source, rows.name
            assert "No records found." not in source, rows.name

    def test_the_script_grows_the_span_instead_of_replacing_it(self):
        """`worktable.js` inyecta la columna de selección, así que la fila vacía
        abarca una más. **Se suma, nunca se pone un número grande**: volver a un
        `colspan` mayor que las columnas reales reproduce el defecto exacto."""
        script = (Path(settings.BASE_DIR) / "static" / "js" / "worktable.js").read_text(
            encoding="utf-8"
        )
        injection = script.split('col.className = "col-select"', 1)[1]

        assert "cell.colSpan = cell.colSpan + 1" in injection
