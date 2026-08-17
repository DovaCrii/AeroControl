"""LV-104: que los documentos aguanten volumen.

Pedido del usuario: *"cuando tengamos mucha información debe ser clara, fácil de
buscar"*. Con el importador de `Z:` en el horizonte —cientos de archivos— una
tabla plana ordenada por fecha deja de servir.

La categoría de `LV-95` ya es la faceta natural, así que esto no inventa una
taxonomía nueva: la usa en los dos sitios donde se busca un documento, la ficha
de un registro (agrupada) y el repositorio de la empresa (filtrable).

Los dos tests que importan son los que fijan errores que **sólo se ven usando la
pantalla**: que el filtro no se coma sus propias opciones, y que el orden de los
grupos sea el declarado y no el alfabético del valor guardado en inglés.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.compliance.attachments import attached_documents_context
from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.tenancy import get_default_tenant
from apps.registry.models import Aircraft

TODAY = date(2026, 8, 14)


def _client(*codenames):
    user = User.objects.create_user("u-facets", password="pw")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _doc_type(code, category):
    return DocumentType.objects.create(
        name=code, code=code, category=category, requires_expiry=False
    )


def _document(subject, doc_type, title, issue_date=TODAY):
    return Document.objects.create(
        title=title,
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(subject),
        object_id=subject.pk,
        issue_date=issue_date,
        file_path=f"{title}.pdf",
    )


@pytest.fixture
def tenant(db):
    return OperationalTenant.objects.get(pk=get_default_tenant())


@pytest.mark.django_db
class TestTheFicheGroupsByCategory:
    def test_groups_come_in_the_declared_order_not_alphabetical(self):
        """El valor guardado está en inglés ("aircraft", "company", "dgac"…), así
        que ordenar por él dejaría la interfaz en español en orden alfabético de
        otro idioma. Manda `CATEGORY_CHOICES`, que es el orden del formulario."""
        aircraft = Aircraft.objects.create(
            registration="RPA-104", type="RPA", model="M3", manufacturer="DJI"
        )
        # Creados al revés del orden declarado, para que pasar por casualidad
        # sea imposible.
        _document(aircraft, _doc_type("proc", DocumentType.CATEGORY_COMPANY), "Manual")
        _document(aircraft, _doc_type("cred", DocumentType.CATEGORY_PERSONNEL), "Cred")
        _document(
            aircraft, _doc_type("mat", DocumentType.CATEGORY_AIRCRAFT), "Matrícula"
        )
        user = User.objects.create_superuser("root-104", "r@test.com", "pw")

        documents = attached_documents_context(user, aircraft)["documents"]

        assert [d.doc_type.category for d in documents] == [
            DocumentType.CATEGORY_PERSONNEL,
            DocumentType.CATEGORY_AIRCRAFT,
            DocumentType.CATEGORY_COMPANY,
        ]

    def test_the_newest_still_comes_first_inside_a_group(self):
        """Agrupar no reemplaza al orden anterior, lo anida."""
        aircraft = Aircraft.objects.create(
            registration="RPA-105", type="RPA", model="M3", manufacturer="DJI"
        )
        doc_type = _doc_type("mat", DocumentType.CATEGORY_AIRCRAFT)
        _document(aircraft, doc_type, "Vieja", date(2026, 1, 1))
        _document(aircraft, doc_type, "Nueva", date(2026, 8, 1))
        user = User.objects.create_superuser("root-105", "r@test.com", "pw")

        documents = attached_documents_context(user, aircraft)["documents"]

        assert [d.title for d in documents] == ["Nueva", "Vieja"]

    def test_the_fiche_draws_one_heading_per_category_and_no_more(self):
        """Se afirma la **estructura**, no el texto: la etiqueta del grupo se
        traduce y la respuesta sale en el idioma del middleware, no en el que
        fije el test (la trampa de `LV-95` y `LV-107`). Dos categorías tienen
        que dar dos encabezados, y tres documentos de la misma sólo uno."""
        aircraft = Aircraft.objects.create(
            registration="RPA-106", type="RPA", model="M3", manufacturer="DJI"
        )
        matricula = _doc_type("mat", DocumentType.CATEGORY_AIRCRAFT)
        _document(aircraft, matricula, "Matrícula")
        _document(aircraft, matricula, "Aeronavegabilidad")
        _document(aircraft, _doc_type("cred", DocumentType.CATEGORY_PERSONNEL), "Cred")

        html = (
            _client("view_aircraft", "view_document")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )

        assert html.count('class="table-active"') == 2
        assert "Matrícula" in html and "Cred" in html


@pytest.mark.django_db
class TestTheCompanyRepositoryFiltersByCategory:
    def test_it_narrows_the_list(self, tenant):
        _document(tenant, _doc_type("aoc", DocumentType.CATEGORY_COMPANY), "AOC")
        _document(tenant, _doc_type("cred", DocumentType.CATEGORY_PERSONNEL), "Cred")
        client = _client("view_document")

        html = client.get(
            reverse("company-documents"), {"category": DocumentType.CATEGORY_COMPANY}
        ).content.decode()

        assert "AOC" in html
        assert "Cred" not in html

    def test_filtering_does_not_eat_the_other_options(self, tenant):
        """El defecto clásico de las facetas: calculadas sobre el resultado ya
        filtrado, elegir una categoría deja esa como única opción y no hay cómo
        cambiar sin editar la URL."""
        _document(tenant, _doc_type("aoc", DocumentType.CATEGORY_COMPANY), "AOC")
        _document(tenant, _doc_type("cred", DocumentType.CATEGORY_PERSONNEL), "Cred")
        client = _client("view_document")

        response = client.get(
            reverse("company-documents"), {"category": DocumentType.CATEGORY_COMPANY}
        )

        offered = {value for value, _label in response.context["categories"]}
        assert offered == {
            DocumentType.CATEGORY_COMPANY,
            DocumentType.CATEGORY_PERSONNEL,
        }

    def test_it_only_offers_categories_that_have_documents(self, tenant):
        """Un filtro con opciones que devuelven vacío enseña a desconfiar."""
        _document(tenant, _doc_type("aoc", DocumentType.CATEGORY_COMPANY), "AOC")
        client = _client("view_document")

        response = client.get(reverse("company-documents"))

        assert [value for value, _label in response.context["categories"]] == [
            DocumentType.CATEGORY_COMPANY
        ]

    def test_a_made_up_category_in_the_url_is_ignored_not_applied(self, tenant):
        """Los parámetros vienen de una URL, o sea que no son de fiar."""
        _document(tenant, _doc_type("aoc", DocumentType.CATEGORY_COMPANY), "AOC")
        client = _client("view_document")

        response = client.get(reverse("company-documents"), {"category": "inventada"})

        assert response.status_code == 200
        assert "AOC" in response.content.decode()
