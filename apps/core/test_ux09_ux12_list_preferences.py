"""UX-09 y UX-12: las columnas de cada persona, y las vistas guardadas.

`UX-09` pide *"un selector de columnas persistido por lista y por persona"*;
`UX-12`, *"un filtro con nombre, propia o compartida"*, que aparezca *"como
pestañas sobre la tabla"*. Las dos son el mismo hecho —con qué estado alguien
vuelve a una lista— y las guarda un solo modelo, `ListPreference`.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.models import ListPreference
from apps.core.testing import login_as

User = get_user_model()


class TestTheModelHoldsBothFeatures:
    @pytest.mark.django_db
    def test_the_same_person_can_have_a_default_and_named_views(self, db):
        """`name` vacío es el registro de `UX-09` —las columnas por omisión— y
        con nombre es una vista de `UX-12`. La restricción única cubre las dos
        formas de una vez, y tiene que dejar convivir ambas."""
        user = User.objects.create_user("ana", password="x")

        ListPreference.objects.create(user=user, list_key="alert-list", name="")
        ListPreference.objects.create(user=user, list_key="alert-list", name="Vencidos")

        assert ListPreference.objects.filter(user=user).count() == 2

    @pytest.mark.django_db
    def test_a_shared_view_needs_a_name(self, db):
        """Una compartida sin nombre sería el registro de columnas por omisión de
        alguien, impuesto a todos: no es una vista, es su configuración
        personal."""
        user = User.objects.create_user("ana", password="x")
        row = ListPreference(user=user, list_key="alert-list", name="", is_shared=True)

        with pytest.raises(ValidationError):
            row.full_clean()

    @pytest.mark.django_db
    def test_it_stores_the_hidden_columns_and_not_the_visible_ones(self, db):
        """⚠️ La decisión del campo, y la que no se ve al leerlo.

        Con las **visibles**, una columna nueva sería invisible para todo el que
        alguna vez guardó una preferencia: la lista estrenaría la columna
        mostrándosela sólo a quien nunca la configuró, que es exactamente al
        revés. El test lo fija por el nombre del campo, que es lo único que
        impide que alguien invierta el criterio sin darse cuenta.
        """
        assert hasattr(ListPreference, "hidden_columns")
        assert not hasattr(ListPreference, "visible_columns")


class TestHidingAColumn:
    @pytest.mark.django_db
    def test_saving_records_it_for_that_person_and_that_list(self, db):
        client = login_as("view_alert")

        response = client.post(
            reverse("list-columns-save"),
            {"list_key": "alert-list", "hidden": ["rule", "triggered"]},
        )

        assert response.status_code == 200
        row = ListPreference.objects.get(list_key="alert-list", name="")
        assert row.hidden_columns == ["rule", "triggered"]

    @pytest.mark.django_db
    def test_saving_again_replaces_instead_of_piling_up(self, db):
        client = login_as("view_alert")

        client.post(
            reverse("list-columns-save"), {"list_key": "alert-list", "hidden": ["rule"]}
        )
        client.post(
            reverse("list-columns-save"),
            {"list_key": "alert-list", "hidden": ["triggered"]},
        )

        assert ListPreference.objects.filter(list_key="alert-list").count() == 1
        assert ListPreference.objects.get().hidden_columns == ["triggered"]

    @pytest.mark.django_db
    def test_it_does_not_require_a_model_permission(self, db):
        """Esconder una columna no cambia ningún dato del negocio: es cómo
        alguien mira su propia pantalla. Pedir `change_alert` para eso
        convertiría una preferencia personal en un privilegio -- y quien sólo
        puede ver es justamente quien más necesita acomodar la vista."""
        client = login_as("view_alert")

        response = client.post(
            reverse("list-columns-save"), {"list_key": "alert-list", "hidden": ["rule"]}
        )

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_the_hidden_set_reaches_the_page(self, db):
        client = login_as("view_alert")
        client.post(
            reverse("list-columns-save"), {"list_key": "alert-list", "hidden": ["rule"]}
        )

        body = client.get(reverse("alert-list")).content.decode()

        assert 'data-hidden-columns="rule"' in body
        # Y el cuerpo espera escondido, para que la tabla no aparezca entera y
        # pierda una columna a la vista.
        assert "wt-pending" in body

    @pytest.mark.django_db
    def test_nothing_hidden_means_nothing_waits(self, db):
        """La enorme mayoría de las cargas. No pueden depender de que el JS corra
        para que la tabla se vea."""
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert "wt-pending" not in body

    @pytest.mark.django_db
    def test_the_columns_carry_their_name_into_the_header(self, db):
        """`data-col` es la identidad que el JS copia a cada celda. Sin ella en
        el `<th>`, esconder no tendría a qué agarrarse."""
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert 'data-col="rule"' in body
        # "Entidad" no ordena y **sí** se puede esconder: son dos capacidades
        # distintas, y ésa es la razón por la que el nombre va aparte de la lista
        # blanca de orden.
        assert 'data-col="entity"' in body


class TestSavedViews:
    @pytest.mark.django_db
    def test_saving_keeps_the_filter_under_a_name(self, db):
        client = login_as("view_alert")

        client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Seguros vencidos",
                "query": "?is_resolved=false&entity_type=aircraft",
                "next": reverse("alert-list"),
            },
        )

        view = ListPreference.objects.get(name="Seguros vencidos")
        assert "entity_type=aircraft" in view.query
        assert view.is_shared is False

    @pytest.mark.django_db
    def test_the_page_number_is_not_part_of_the_view(self, db):
        """Una vista que arrastra "página 3" devuelve la página 3 de un conjunto
        que ya cambió. Y una que arrastra `view` se apuntaría a sí misma."""
        client = login_as("view_alert")

        client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Vencidos",
                "query": "?is_resolved=false&page=3&view=abc",
                "next": reverse("alert-list"),
            },
        )

        view = ListPreference.objects.get(name="Vencidos")
        assert "page=" not in view.query
        assert "view=" not in view.query

    @pytest.mark.django_db
    def test_it_appears_as_a_tab_over_the_table(self, db):
        """El criterio de `UX-12`, literal."""
        client = login_as("view_alert")
        client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Seguros vencidos",
                "query": "?is_resolved=false",
                "next": reverse("alert-list"),
            },
        )

        body = client.get(reverse("alert-list")).content.decode()

        assert "Seguros vencidos" in body
        assert "worktable-view" in body

    @pytest.mark.django_db
    def test_saving_the_same_name_updates_instead_of_duplicating(self, db):
        """Dos vistas llamadas igual con filtros distintos es la forma más rápida
        de que nadie confíe en ninguna."""
        client = login_as("view_alert")
        for query in ("?is_resolved=false", "?is_resolved=true"):
            client.post(
                reverse("list-view-save"),
                {
                    "list_key": "alert-list",
                    "name": "Vencidos",
                    "query": query,
                    "next": reverse("alert-list"),
                },
            )

        assert ListPreference.objects.filter(name="Vencidos").count() == 1
        assert ListPreference.objects.get(name="Vencidos").query == "is_resolved=true"

    @pytest.mark.django_db
    def test_a_view_without_a_name_is_refused(self, db):
        client = login_as("view_alert")

        client.post(
            reverse("list-view-save"),
            {"list_key": "alert-list", "name": "", "next": reverse("alert-list")},
        )

        assert not ListPreference.objects.exclude(name="").exists()


class TestSharingIsOfferingAndNotCeding:
    @pytest.mark.django_db
    def test_a_shared_view_is_visible_to_someone_else(self, db):
        other = User.objects.create_user("otro", password="x")
        ListPreference.objects.create(
            user=other,
            list_key="alert-list",
            name="De todos",
            query="is_resolved=false",
            is_shared=True,
        )
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert "De todos" in body

    @pytest.mark.django_db
    def test_a_private_view_of_someone_else_is_not(self, db):
        other = User.objects.create_user("otro", password="x")
        ListPreference.objects.create(
            user=other, list_key="alert-list", name="Solo mia", is_shared=False
        )
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert "Solo mia" not in body

    @pytest.mark.django_db
    def test_only_its_author_can_delete_a_shared_view(self, db):
        """Compartir es ofrecer, no ceder. Y el filtro por autor está en la
        consulta y no en un `if` posterior: la segunda forma es la que alguien
        "simplifica" después."""
        other = User.objects.create_user("otro", password="x")
        view = ListPreference.objects.create(
            user=other, list_key="alert-list", name="De todos", is_shared=True
        )
        client = login_as("view_alert")

        response = client.post(reverse("list-view-delete", args=[view.pk]))

        assert response.status_code == 404
        assert ListPreference.objects.filter(pk=view.pk).exists()

    @pytest.mark.django_db
    def test_its_author_can(self, db):
        client = login_as("view_alert")
        client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Mia",
                "next": reverse("alert-list"),
            },
        )
        view = ListPreference.objects.get(name="Mia")

        client.post(
            reverse("list-view-delete", args=[view.pk]),
            {"next": reverse("alert-list")},
        )

        assert not ListPreference.objects.filter(pk=view.pk).exists()


class TestNextIsNotAnOpenRedirect:
    """⚠️ Sin comprobarlo, `next=https://otro-sitio/` convertiría "guardar una
    vista" en un redirector abierto: un enlace que **sale de AeroControl** y por
    eso parece de confianza, hacia una pantalla de acceso copiada."""

    @pytest.mark.django_db
    def test_an_external_next_is_ignored(self, db):
        client = login_as("view_alert")

        response = client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Mia",
                "next": "https://ejemplo-malicioso.invalid/entrar",
            },
        )

        assert "ejemplo-malicioso" not in response["Location"]

    @pytest.mark.django_db
    def test_an_internal_next_is_honoured(self, db):
        client = login_as("view_alert")

        response = client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Mia",
                "next": reverse("alert-list"),
            },
        )

        assert response["Location"] == reverse("alert-list")


class TestAViewCarriesItsOwnColumns:
    @pytest.mark.django_db
    def test_opening_a_view_uses_the_columns_it_was_saved_with(self, db):
        """Volver a "Seguros vencidos" con las columnas de otra vista sería
        devolver algo que no es lo que se guardó."""
        client = login_as("view_alert")
        client.post(
            reverse("list-columns-save"),
            {"list_key": "alert-list", "hidden": ["rule"]},
        )
        client.post(
            reverse("list-view-save"),
            {
                "list_key": "alert-list",
                "name": "Vencidos",
                "hidden": ["triggered", "expiry"],
                "next": reverse("alert-list"),
            },
        )
        view = ListPreference.objects.get(name="Vencidos")

        body = client.get(
            reverse("alert-list"), {"view": str(view.pk)}
        ).content.decode()

        assert 'data-hidden-columns="triggered,expiry"' in body
