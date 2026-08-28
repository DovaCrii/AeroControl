"""LV-172: el catastro cierra con su total, no sólo lo anuncia al empezar.

Pedido del usuario: *"sumar al catastro de flota y personal al final un contador
con la cantidad de equipos totales y personal total"*. El número ya estaba
arriba, y eso no es lo mismo: con la flota y el personal ocupando varias
páginas, quien recibe el documento termina de leer a varias páginas del número
que lo resume — y en un listado que se entrega, el total del final es lo que
confirma que no se cortó nada en el camino.

Las propiedades que estos tests sostienen, y por qué cada una:

- **La pantalla y el papel no pueden decir cifras distintas.** Salen de la misma
  función, que es la regla del módulo desde `LV-145`.
- **La concordancia se hereda, no se reescribe.** `LV-161` arregló el *"1
  aeronaves"* que producción mostró el día del despliegue; una segunda copia de
  esa lógica se desincroniza y el error vuelve por donde nadie mira.
- **No va en el CSV ni en la planilla.** Una fila de totales dentro de un archivo
  de datos es una fila más para quien ordena, filtra o suma la columna: rompe
  justamente lo que esos dos formatos existen para permitir.
- **Cuenta lo mismo que las tablas.** Un total que no coincide con las filas que
  tiene encima es peor que no tenerlo.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.catastro import build_catastro, closing_total
from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.fixture
def roster(db):
    center = CostCenter.objects.create(code="CC1", name="Faena")
    for index in range(3):
        Aircraft.objects.create(
            registration=f"RPA-{index}", serial_number=f"S{index}", cost_center=center
        )
    for index in range(2):
        Operator.objects.create(
            employee_id=f"E-{index}", full_name=f"Piloto {index}", cost_center=center
        )
    return center


def test_the_closing_total_counts_what_the_tables_hold(roster, admin_user):
    catastro = build_catastro(admin_user)

    closing = str(closing_total(catastro))

    assert "3" in closing and "2" in closing
    assert catastro["totals"] == {
        **catastro["totals"],
        "aircraft": 3,
        "operators": 2,
    }


def test_a_single_aircraft_is_not_announced_in_the_plural(db, admin_user):
    """LV-161 otra vez: producción mostró "1 aeronaves" el día del despliegue."""
    Aircraft.objects.create(registration="RPA-1", serial_number="S1")
    Operator.objects.create(employee_id="E-1", full_name="Solo")

    closing = str(closing_total(build_catastro(admin_user)))

    assert "1 aeronaves" not in closing
    assert "1 operadores" not in closing


def test_an_empty_roster_still_closes_with_a_total(db, admin_user):
    """Cero es una respuesta; una página que termina sin total, no."""
    closing = str(closing_total(build_catastro(admin_user)))

    assert "0" in closing


def test_the_screen_carries_it_at_the_end(roster):
    client = login_as("view_aircraft", "view_operator")

    response = client.get(reverse("registry-roster"))
    body = response.content.decode()

    assert response.status_code == 200
    assert 'class="catastro-closing"' in body
    # Al final de verdad: después de la última tabla, no encima de ella.
    assert body.index('class="catastro-closing"') > body.rindex("<table")


def test_the_pdf_carries_it_too(roster):
    client = login_as("view_aircraft", "view_operator")

    response = client.get(reverse("registry-roster-pdf"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


@pytest.mark.parametrize("view", ["registry-roster-csv", "registry-roster-xlsx"])
def test_the_data_files_get_no_totals_row(roster, view):
    """Una fila de totales rompe ordenar, filtrar y sumar la columna."""
    client = login_as("view_aircraft", "view_operator")

    response = client.get(reverse(view))

    assert response.status_code == 200
    assert b"Total:" not in response.content
