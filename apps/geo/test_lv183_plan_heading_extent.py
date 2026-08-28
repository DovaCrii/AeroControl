"""LV-183: el encabezado del plan dice de qué tamaño es el área.

Pedido del usuario mirando la hoja de campo: *"sumar acá el radio de la
circunferencia"*. El radio **ya estaba** en la hoja, pero al final, bajo
"Circunferencia y aeródromo", porque esa hoja sigue el orden del formulario de
SIGO — que es correcto para transcribir casilla por casilla y malo para responder
"¿de qué tamaño es esto?" al abrir el plan. Arriba no había nada del tamaño.

**No se repite el número dentro de la hoja**, que era la otra salida posible: hay
**dos radios distintos** en juego —el del círculo envolvente y el promedio de lo
dibujado— y en una pantalla cuyo propósito es copiar sin equivocarse, el mismo
dato dos veces a dos centímetros es una oportunidad de copiar el que no era.

Las propiedades que estos tests sostienen:

- **Un círculo envolvente se declara como tal.** El radio del círculo que cubre
  un área dibujada no es el radio del área; afirmarlo a secas es el error que
  `LV-132` nombró.
- **Con varias circunferencias se dice cuántas, no el radio de una.** Ahí la
  pregunta del encabezado deja de ser el tamaño y pasa a ser cuántas separar, y
  elegir una afirmaría que las demás no existen.
- **Sin radio no se inventa nada.**
"""

import pytest

from apps.geo.views import _heading_extent


def test_one_circle_shows_its_radius():
    extent = _heading_extent([{"radius_m": 3115, "is_enclosing": False}])

    assert extent == {"radius_m": 3115, "is_enclosing": False}


def test_an_enclosing_circle_says_that_it_encloses():
    """El radio del círculo que cubre el área no es el radio del área."""
    extent = _heading_extent([{"radius_m": 3115, "is_enclosing": True}])

    assert extent["is_enclosing"] is True


def test_several_circles_are_counted_instead_of_picking_one():
    """Elegir el radio de una afirmaría que las demás no están."""
    rows = [
        {"radius_m": 300, "is_enclosing": False},
        {"radius_m": 900, "is_enclosing": False},
    ]

    assert _heading_extent(rows) == {"count": 2}


def test_a_plan_without_sections_says_nothing():
    assert _heading_extent([]) is None


def test_a_circle_without_a_radius_says_nothing():
    """Un plan puede no tener radio calculado; inventarlo sería peor que callar."""
    assert _heading_extent([{"radius_m": None, "is_enclosing": False}]) is None


@pytest.mark.django_db
def test_the_heading_carries_it_on_the_page(client, django_user_model):
    """Y llega a la pantalla, que es donde el usuario lo pidió."""
    from django.urls import reverse

    from apps.core.testing import login_as
    from apps.geo.models import GeoPlan
    from apps.registry.models import CostCenter

    author = django_user_model.objects.create_user("planner", password="x")
    plan = GeoPlan.objects.create(
        title="CG-01",
        cost_center=CostCenter.objects.create(code="CC1", name="Faena"),
        created_by=author,
    )
    logged = login_as("view_geoplan")

    response = logged.get(reverse("geo-plan-detail", args=[plan.pk]))

    # Sin versión no hay secciones, así que el encabezado calla en vez de
    # inventar un tamaño -- y la página sigue abriendo.
    assert response.status_code == 200
    assert response.context["heading_extent"] is None
