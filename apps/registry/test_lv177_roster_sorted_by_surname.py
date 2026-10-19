"""LV-177: el padrón se ordena por apellido, sin inventar dónde empieza.

Observación del usuario sobre la lista de Operadores: *"mejorar la distribución y
cómo se representa esta página y el orden"*. Estaba ordenada por `full_name`, que
es un solo campo: alfabéticamente eso ordena por el **nombre de pila** —Alberto,
Alex, Alexandra, Aldo, Boris…— y a alguien se lo busca por el apellido. Con 42
personas hay que barrer la lista entera.

**El corte no se deduce.** "Juan Luis Ogando Herrada" son dos nombres y dos
apellidos; "Marianne Von Brandt Keller" lleva partícula; "Ana Rivas" es uno y
uno. Partir por espacios acierta en el caso fácil y se equivoca en el raro — que
es justo el que cuesta encontrar— y nadie lo nota, porque la lista igual se ve
ordenada. Por eso los campos nacen vacíos y hay un comando que **propone**.

Las propiedades que estos tests sostienen:

- **Nadie desaparece mientras se completa.** Sin apellido cargado, la ficha
  ordena por su nombre completo y cae donde alguien la busca hoy.
- **El nombre de registro no cambia.** `full_name` es el que sale en el permiso,
  el catastro y el PDF; estos campos sólo ordenan y presentan.
- **Un apellido que no está en el nombre completo se rechaza.** Es la única
  forma de que la ficha termine diciendo dos nombres para la misma persona.
- **El comando propone y no decide**, y lo ambiguo lo reporta en vez de tocarlo.
"""

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.management.commands.split_operator_names import propose
from apps.registry.models import Operator


def _operator(full_name, **kwargs):
    return Operator.objects.create(
        employee_id=f"E-{full_name[:6]}", full_name=full_name, **kwargs
    )


@pytest.mark.django_db
def test_the_roster_sorts_by_surname_when_it_is_known():
    _operator(
        "Mario Elias Arce Mella", given_names="Mario Elias", surnames="Arce Mella"
    )
    _operator(
        "Sebastian Muñiz Montero", given_names="Sebastian", surnames="Muñiz Montero"
    )
    _operator("Aldo Orrego Rebolledo", given_names="Aldo", surnames="Orrego Rebolledo")
    client = login_as("view_operator")

    body = client.get(reverse("operator-list")).content.decode()

    assert (
        body.index("Arce Mella")
        < body.index("Muñiz Montero")
        < body.index("Orrego Rebolledo")
    )


@pytest.mark.django_db
def test_a_record_without_the_split_still_appears_where_it_is_looked_for():
    """Nadie desaparece mientras se completa el padrón."""
    _operator("Ana Rivas")
    _operator(
        "Sebastian Muñiz Montero", given_names="Sebastian", surnames="Muñiz Montero"
    )
    client = login_as("view_operator")

    body = client.get(reverse("operator-list")).content.decode()

    # "Ana Rivas" ordena por su nombre completo: cae antes de "Muñiz Montero".
    assert body.index("Ana Rivas") < body.index("Muñiz Montero")


@pytest.mark.django_db
def test_the_listing_shows_the_surname_first_only_when_it_is_known():
    split = _operator(
        "Sebastian Muñiz Montero", given_names="Sebastian", surnames="Muñiz Montero"
    )
    plain = _operator("Ana Rivas")

    assert split.listing_name == "Muñiz Montero, Sebastian"
    assert plain.listing_name == "Ana Rivas"


@pytest.mark.django_db
def test_the_full_name_stays_the_name_on_record():
    """Es el que sale en el permiso, el catastro y el PDF."""
    operator = _operator(
        "Sebastian Muñiz Montero", given_names="Sebastian", surnames="Muñiz Montero"
    )

    assert str(operator) == "Sebastian Muñiz Montero"


@pytest.mark.django_db
def test_a_surname_that_is_not_in_the_full_name_is_refused():
    """Si no, la ficha dice dos nombres distintos para la misma persona."""
    operator = Operator(
        employee_id="E-1", full_name="Ana Rivas", given_names="Ana", surnames="Soto"
    )

    with pytest.raises(ValidationError) as error:
        operator.full_clean()

    assert "surnames" in error.value.error_dict


@pytest.mark.django_db
def test_accents_and_case_do_not_make_it_refuse():
    """Quien complete el corte lo tipea a mano; un acento no es un error."""
    operator = Operator(
        employee_id="E-1",
        full_name="Sebastian Muñiz Montero",
        given_names="sebastian",
        surnames="MUNIZ montero",
    )

    operator.full_clean()  # no levanta


def test_the_command_proposes_the_chilean_pattern():
    assert propose("Aldo Orrego Rebolledo") == ("Aldo", "Orrego Rebolledo")
    assert propose("Juan Luis Ogando Herrada") == ("Juan Luis", "Ogando Herrada")


def test_the_command_refuses_to_guess_what_it_cannot_know():
    """Reportar de más antes que escribir de más."""
    assert propose("Ana Rivas") is None, "dos palabras no dicen cuál es cuál"
    assert propose("Marianne Von Brandt Keller") is None, "la partícula rompe el conteo"
    assert propose("Maria Jose de la Cruz Soto") is None


@pytest.mark.django_db
def test_the_command_writes_nothing_without_apply():
    operator = _operator("Aldo Orrego Rebolledo")

    call_command("split_operator_names", stdout=StringIO())

    operator.refresh_from_db()
    assert operator.surnames == ""


@pytest.mark.django_db
def test_the_command_writes_the_proposals_with_apply_and_leaves_the_rest():
    clear = _operator("Aldo Orrego Rebolledo")
    ambiguous = _operator("Marianne Von Brandt Keller")
    out = StringIO()

    call_command("split_operator_names", "--apply", stdout=out)

    clear.refresh_from_db()
    ambiguous.refresh_from_db()
    assert clear.surnames == "Orrego Rebolledo"
    assert ambiguous.surnames == "", "lo ambiguo se reporta, no se toca"
    assert "Marianne Von Brandt Keller" in out.getvalue()
