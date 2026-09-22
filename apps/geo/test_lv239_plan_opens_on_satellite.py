"""LV-239: el plan abre en satélite, y eso deja de depender del orden de una lista.

Pedido del usuario el 2026-09-21, mirando la ficha de un plan: *"al ingresar al plan
que siempre parta en satélite"*. El área de un plan es terreno —un tranque, una
ladera, un rajo— y sobre el callejero la circunferencia queda flotando en blanco: hay
que cambiar de capa antes de poder mirar nada, y hay que hacerlo todas las veces.

⚠️ **Lo que se arregla no es sólo cuál capa sale.** El editor dibujaba *"la primera de
`GEO_TILE_PROVIDERS`"*, así que la capa inicial era un efecto del **orden** de un
literal de configuración: reordenarlo por prolijidad —o insertar un proveedor nuevo
arriba— cambiaba en silencio lo que ve el operador al abrir un plan, y ni el ajuste ni
`static/js/geo/map.js` lo decían en ninguna parte. Ahora manda una marca explícita, y
estos tests son los que impiden que vuelva a ser implícito.
"""

import pytest
from django.conf import settings


def _providers():
    return settings.GEO_TILE_PROVIDERS


class TestTheDefaultLayerIsDeclaredAndNotInferred:
    def test_satellite_is_the_one_marked_as_default(self):
        marked = [p for p in _providers() if p.get("default")]

        assert [p["id"] for p in marked] == ["satellite"]

    def test_exactly_one_provider_is_marked(self):
        """Dos marcados harían que ganara el primero otra vez, que es justo el
        comportamiento implícito del que esta fila viene saliendo."""
        assert sum(1 for p in _providers() if p.get("default")) == 1

    def test_the_default_is_not_merely_the_first_in_the_list(self):
        """⚠️ **El test que le da sentido a los otros dos.**

        Si algún día el satélite quedara además primero en la lista, los dos de
        arriba seguirían pasando **aunque el editor hubiera vuelto a elegir por
        orden**: la marca y la posición coincidirían y el defecto sería invisible.

        Que el proveedor por defecto **no** sea el primero es lo que mantiene a las
        dos reglas distinguibles, así que el orden de `GEO_TILE_PROVIDERS` se
        conserva a propósito — sólo decide el orden del selector, que es cosmético.
        """
        providers = _providers()

        assert providers[0]["id"] != "satellite"
        assert providers[0]["id"] == "streets"


class TestTheEditorReadsTheFlag:
    def test_the_island_still_receives_every_provider(self):
        """La marca elige cuál se dibuja, **no** recorta el selector: el callejero
        sigue estando a un clic, que es lo que el usuario usa para ubicarse por
        caminos y nombres de lugar."""
        assert {p["id"] for p in _providers()} == {"streets", "satellite"}

    def test_the_javascript_picks_the_flagged_one(self):
        """Se afirma sobre el archivo porque el proyecto no tiene corredor de
        JavaScript, y sin esto la mitad que de verdad dibuja el mapa no está
        cubierta por nada: el ajuste podría quedar marcado y el editor seguir
        tomando el primero, que es el estado exacto del que se viene."""
        from pathlib import Path

        source = (
            Path(settings.BASE_DIR) / "static" / "js" / "geo" / "map.js"
        ).read_text(encoding="utf-8")

        assert "provider.default" in source
        # Y que conserve el respaldo: sin ninguno marcado, el mapa igual se dibuja.
        assert "providers[0]" in source


@pytest.mark.django_db
def test_the_plan_page_carries_the_flag_to_the_browser(client, django_user_model):
    """De punta a punta: la marca llega al `tileProviders` que el editor lee.

    Es la única forma de comprobar que el ajuste y la isla siguen conectados — el
    resto de este archivo mira cada mitad por separado.
    """
    from apps.geo.models import GeoPlan
    from apps.registry.models import CostCenter

    user = django_user_model.objects.create_superuser("geo-user", "g@test.com", "pw")
    assert client.login(username="geo-user", password="pw")
    plan = GeoPlan.objects.create(
        title="Plan",
        created_by=user,
        cost_center=CostCenter.objects.create(code="CC738", name="Faena"),
    )

    response = client.get(plan.get_absolute_url())

    assert response.status_code == 200
    providers = response.context["map_config"]["tileProviders"]
    assert [p["id"] for p in providers if p.get("default")] == ["satellite"]
