"""LV-103 paso 1: el calendario se queda sin superficies, sin borrar nada.

Decisión del usuario (2026-08-14): *"no lo utilizo, me estoy guiando de alertas
principalmente"*. Se retira con el procedimiento de `LV-78` —sin menú, después
congelado, y sólo al final borrarlo si nadie lo echa de menos—, que es lo que
separa "dejar de ofrecerlo" de "destruirlo".

Los dos tests de abajo son las dos mitades de ese paso, y ninguno sirve solo:
sin el primero el retiro no ocurrió, y sin el segundo no es un retiro sino un
borrado a medias, con una URL viva que ya nadie puede probar.
"""

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse


def _client(*codenames):
    user = User.objects.create_user("u-calendar", password="pw")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


@pytest.mark.django_db
def test_the_menu_no_longer_offers_the_calendar():
    client = _client("view_flightpermission")

    content = client.get(reverse("permission-list")).content.decode()

    assert reverse("calendar") not in content


@pytest.mark.django_db
def test_but_the_calendar_still_works_for_whoever_goes_there_directly():
    """Congelado, no borrado. Si mañana se decide que hacía falta, alcanza con
    devolver el enlace -- y mientras tanto, quien tenga el enlace guardado no se
    encuentra con un 404 sin explicación."""
    client = _client("view_flightpermission")

    assert client.get(reverse("calendar")).status_code == 200
    assert client.get(reverse("calendar-events")).status_code == 200
