"""`UX-07`, primera pieza: "mostrando N–M de T" en toda lista paginada.

**La paginación entera desaparecía con una sola página** (`has_other_pages`), así
que una lista de ocho filas no decía si eran ocho de ocho o **ocho de doscientas
filtradas**. El número que faltaba no era el de páginas: era el **total**, y es
el que contesta *"¿me estoy perdiendo algo?"* — la pregunta que alguien se hace
justo antes de dar por buena una revisión de cumplimiento.

Entra en `generic/_pagination.html`, que es el parcial que **todas** las listas
paginadas ya incluían, así que las doce lo ganan a la vez sin tocar ninguna.
"""

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


class TestTheCountIsAlwaysThere:
    @pytest.mark.django_db
    def test_it_shows_even_with_a_single_page(self, client, reader):
        """**El caso que motiva la fila.**

        Con una sola página la paginación no se dibujaba, así que el total no
        aparecía en ningún lado — y es justo la lista corta la que más invita a
        creer que se está viendo todo.
        """
        for index in range(3):
            CostCenter.objects.create(code=f"CC{index}", name=f"Faena {index}")
        client.force_login(reader)

        body = client.get(reverse("costcenter-list")).content.decode()

        assert "list-count" in body
        assert "1–3" in body or "1&ndash;3" in body

    @pytest.mark.django_db
    def test_with_nothing_to_show_it_stays_quiet(self, client, reader):
        """La tabla ya tiene su propia fila de vacío, y dos mensajes para el
        mismo hecho es ruido."""
        client.force_login(reader)

        body = client.get(reverse("costcenter-list")).content.decode()

        assert "list-count" not in body

    @pytest.mark.django_db
    def test_the_total_is_the_filtered_total_and_not_the_table(self, client, reader):
        """**Lo que hace útil al número.**

        Si contara la tabla entera, diría "3 de 40" mientras el filtro muestra
        3 de 3 y el usuario creería que se está perdiendo 37 que en realidad
        excluyó a propósito. El total tiene que ser el del `queryset` ya
        filtrado, que es lo que el paginador recibe.
        """
        CostCenter.objects.create(code="CC738", name="MLP")
        for index in range(4):
            CostCenter.objects.create(code=f"CX{index}", name=f"Otra {index}")
        client.force_login(reader)

        body = client.get(reverse("costcenter-list"), {"q": "MLP"}).content.decode()

        assert "1–1" in body or "1&ndash;1" in body
        assert "de 5" not in body
