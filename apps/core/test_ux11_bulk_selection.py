"""`UX-11`: selección explícita por casilla, y exportar lo marcado.

⚠️ **La selección es explícita y no se infiere, y eso es la fila entera.**
`LV-68` retiró la resolución en lote que agrupaba alertas por regla y fecha,
sobre la premisa de que una fecha compartida implicaba una causa compartida;
contra los datos reales resultó falsa. Acá no se deduce nada: lo que se exporta
es lo que la persona marcó.

**El test que más importa de este archivo es el del aislamiento.** Los `ids`
llegan de la URL, así que la tentación es `Model.objects.filter(pk__in=ids)` — y
eso se saltaría el filtro por tenant y por permisos que `get_queryset` aplica,
convirtiendo una lista pegada a mano en una forma de exportar filas ajenas. El
recorte se aplica **sobre** el queryset de la vista, nunca en su lugar.
"""

import uuid

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.registry.models import CostCenter


@pytest.fixture
def reader(db):
    user = User.objects.create_user("lector", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_costcenter", content_type__app_label="registry"
        )
    )
    return user


def _body(response):
    """El CSV completo, **leído una sola vez**.

    La exportación transmite por trozos —`render_csv_response` devuelve un
    `StreamingHttpResponse` para no materializar la tabla entera en memoria—,
    así que `response.content` no existe y `streaming_content` es un generador
    que **se agota**. Leerlo dos veces devuelve vacío la segunda, que fue el
    primer resultado de este archivo: un test daba 0 filas donde había 1, y el
    fallo parecía del filtro y era del test. Se guarda en la respuesta.
    """
    if not hasattr(response, "_csv_cache"):
        response._csv_cache = b"".join(response.streaming_content).decode()
    return response._csv_cache


def _rows(response):
    return [line for line in _body(response).splitlines() if line.strip()][1:]


class TestTheExportRespectsTheSelection:
    @pytest.mark.django_db
    def test_without_ids_it_exports_everything_as_before(self, client, reader):
        """La selección **añade** un camino; no reemplaza el que había."""
        for index in range(3):
            CostCenter.objects.create(code=f"CC{index}", name=f"Faena {index}")
        client.force_login(reader)

        response = client.get(reverse("costcenter-list"), {"export": "csv"})

        assert len(_rows(response)) == 3

    @pytest.mark.django_db
    def test_with_ids_it_exports_only_those(self, client, reader):
        chosen = CostCenter.objects.create(code="CC738", name="MLP")
        CostCenter.objects.create(code="CC691", name="El Mauro")
        CostCenter.objects.create(code="CC684", name="Otra")
        client.force_login(reader)

        response = client.get(
            reverse("costcenter-list"), {"export": "csv", "ids": [str(chosen.pk)]}
        )
        body = _body(response)

        assert "CC738" in body
        assert "CC691" not in body
        assert len(_rows(response)) == 1


class TestTheIdsCannotWidenWhatYouCanSee:
    @pytest.mark.django_db
    def test_an_id_outside_the_view_queryset_is_not_exported(self, client, reader):
        """**El test que más importa.**

        Se comprueba con un id **real y existente** que el filtro de la vista
        deja fuera: si el recorte se aplicara al modelo en vez de al queryset,
        esta fila saldría en el CSV. Un id inventado no probaría nada — no
        existe, así que no aparecería de ninguna manera.
        """
        visible = CostCenter.objects.create(code="CC738", name="MLP")
        hidden = CostCenter.objects.create(
            code="CC999", name="Archivada", is_active=False
        )
        client.force_login(reader)

        response = client.get(
            reverse("costcenter-list"),
            {
                "export": "csv",
                "is_active": "active",
                "ids": [str(visible.pk), str(hidden.pk)],
            },
        )
        body = _body(response)

        assert "CC738" in body
        assert "CC999" not in body

    @pytest.mark.django_db
    def test_a_malformed_id_does_not_break_the_export(self, client, reader):
        """Los ids llegan de la URL: una lista con basura tiene que exportar lo
        que sí existe en vez de devolver un 500."""
        chosen = CostCenter.objects.create(code="CC738", name="MLP")
        client.force_login(reader)

        response = client.get(
            reverse("costcenter-list"),
            {"export": "csv", "ids": ["no-soy-un-uuid", str(chosen.pk)]},
        )

        assert response.status_code == 200
        assert "CC738" in _body(response)

    @pytest.mark.django_db
    def test_an_all_invalid_selection_exports_nothing_and_not_everything(
        self, client, reader
    ):
        """**La distinción que evita un CSV entero por error.**

        "No encontré nada de lo que marcaste" no es lo mismo que "no marcaste
        nada". Si una selección inválida cayera al camino sin `ids`, alguien que
        marcó tres filas se llevaría la tabla completa sin notarlo.
        """
        CostCenter.objects.create(code="CC738", name="MLP")
        client.force_login(reader)

        response = client.get(
            reverse("costcenter-list"), {"export": "csv", "ids": ["basura"]}
        )

        assert response.status_code == 200
        assert "CC738" not in _body(response)

    @pytest.mark.django_db
    def test_a_valid_uuid_of_another_model_exports_nothing(self, client, reader):
        CostCenter.objects.create(code="CC738", name="MLP")
        client.force_login(reader)

        response = client.get(
            reverse("costcenter-list"), {"export": "csv", "ids": [str(uuid.uuid4())]}
        )

        assert _rows(response) == []


class TestTheSelectionIsExplicitInTheMarkup:
    def test_the_row_declares_its_own_identity(self):
        """Sin `data-pk`, la selección tendría que deducir el pk del `href` de
        la primera celda — que no existe en las listas sin ficha de detalle."""
        from pathlib import Path

        from django.conf import settings

        partial = (
            Path(settings.BASE_DIR) / "templates" / "generic" / "_table_body.html"
        ).read_text(encoding="utf-8")

        assert 'data-pk="{{ object.pk }}"' in partial

    def test_the_bar_is_hidden_until_something_is_chosen(self):
        """Una barra permanente que dice "0 seleccionados" ocupa sitio todos los
        días para avisar de nada."""
        from pathlib import Path

        from django.conf import settings

        markup = (
            Path(settings.BASE_DIR) / "templates" / "generic" / "list.html"
        ).read_text(encoding="utf-8")

        assert 'id="bulk-bar"' in markup
        assert "hidden" in markup.split('id="bulk-bar"')[1][:120]

    def test_the_count_string_lives_in_the_catalogue(self):
        """Armar la frase en JS habría dejado ese texto fuera del catálogo, que
        es la mitad de la interfaz bilingüe."""
        from pathlib import Path

        from django.conf import settings

        markup = (
            Path(settings.BASE_DIR) / "templates" / "generic" / "list.html"
        ).read_text(encoding="utf-8")

        assert 'blocktranslate asvar bulk_template with n="{n}"' in markup

    def test_every_list_partial_declares_the_identity(self):
        """**Sin esto la función alcanzaba una sola lista.**

        Diez de las once listas reescriben `table_body` y delegan sus filas en
        un parcial `_*_rows.html`, así que tocar sólo el genérico habría dejado
        la selección visible en `record_list` y en ninguna más. Se cuenta sobre
        el árbol para que un parcial nuevo sin `data-pk` caiga acá en vez de
        aparecer sin casillas y que nadie sepa por qué.
        """
        from pathlib import Path

        from django.conf import settings

        missing = []
        for path in (Path(settings.BASE_DIR) / "templates").rglob("*_rows.html"):
            source = path.read_text(encoding="utf-8")
            if "<tr" in source and "data-pk" not in source:
                missing.append(path.name)

        assert not missing, "parciales de fila sin identidad: " + ", ".join(missing)

    def test_the_checkboxes_are_injected_only_where_the_row_knows_itself(self):
        from pathlib import Path

        from django.conf import settings

        script = (Path(settings.BASE_DIR) / "static" / "js" / "worktable.js").read_text(
            encoding="utf-8"
        )

        assert 'querySelector("tr[data-pk]")' in script
