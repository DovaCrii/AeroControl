"""LV-145: the fleet and personnel roster, data layer.

Written against `catastro.py` alone, with no views involved: the four outputs
(screen, PDF, XLSX, CSV) all read this, so what has to be true is true here or
it is true in four places by coincidence.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from apps.core.models import OperationalTenant, TenantMembership
from .catastro import (
    BLANK,
    CatastroFilters,
    aircraft_rows,
    build_catastro,
    operator_rows,
    totals_sentence,
)
from .models import Aircraft, CostCenter, Operator


@pytest.fixture
def root(db):
    """A superuser, i.e. "every tenant" as far as scoping is concerned.

    `build_catastro` takes the user positionally and without a default on
    purpose, so the tenant scope can never be skipped by omission; the tests
    that are not about tenancy pass this and stay about their own subject.
    """
    return User.objects.create_superuser("root", "root@test.com", "password")


@pytest.fixture
def world(db):
    """Two faenas, one aircraft and one operator loose, plus a retired airframe
    and an archived operator -- one row per rule this module has."""
    north = CostCenter.objects.create(code="CC738", name="Los Pelambres")
    south = CostCenter.objects.create(code="CC861", name="Talabre")

    def aircraft(registration, **kwargs):
        return Aircraft.objects.create(
            registration=registration,
            type=kwargs.pop("type", "Multirotor"),
            model=kwargs.pop("model", "Matrice 4 Enterprise"),
            manufacturer=kwargs.pop("manufacturer", "DJI"),
            **kwargs,
        )

    def operator(full_name, employee_id, **kwargs):
        return Operator.objects.create(
            full_name=full_name, employee_id=employee_id, **kwargs
        )

    aircraft("RPA-7126", cost_center=north, serial_number="1581F5FHC245", year=2025)
    aircraft("RPA-5532", cost_center=south)
    aircraft("RPA-9001")  # no cost center
    aircraft("RPA-0001", cost_center=north, status="retired")
    aircraft("RPA-0002", cost_center=north, is_active=False)

    operator("Ana Rivas", "E-001", cost_center=north, rut="12345678-5")
    operator("Bruno Soto", "E-002", cost_center=south)
    operator("Carla Diaz", "E-003")  # no cost center
    operator("Dario Luna", "E-004", cost_center=north, is_active=False)
    return {"north": north, "south": south}


def _registrations(catastro):
    return [aircraft.registration for aircraft in catastro["aircraft"]]


def _names(catastro):
    return [operator.full_name for operator in catastro["operators"]]


# -- what the roster is by default -----------------------------------------


def test_the_default_roster_is_what_is_on_the_books(world, root):
    catastro = build_catastro(root)

    # Alphabetical by registration and by full name, the same order the two
    # list screens use -- so the paper can be read against the screen.
    assert _registrations(catastro) == ["RPA-5532", "RPA-7126", "RPA-9001"]
    assert _names(catastro) == ["Ana Rivas", "Bruno Soto", "Carla Diaz"]
    assert catastro["totals"]["aircraft"] == 3
    assert catastro["totals"]["operators"] == 3


def test_the_cut_off_date_is_declared_and_is_today(world, root):
    catastro = build_catastro(root)

    assert catastro["as_of"] == timezone.localdate()
    assert catastro["as_of"].isoformat() in totals_sentence(catastro)[0]


def test_retired_airframes_are_out_unless_they_are_asked_for(world, root):
    assert "RPA-0001" not in _registrations(build_catastro(root))

    included = build_catastro(root, CatastroFilters(include_terminal=True))

    assert "RPA-0001" in _registrations(included)


def test_the_terminal_status_comes_from_the_model_and_not_from_a_literal():
    """`Aircraft.TERMINAL_STATUSES` is the owner of "which statuses mean the
    airframe left". The day a second one exists, a hard-coded "retired" here
    would keep counting aircraft that are gone -- the same trap LV-90 fixed in
    `generate_alerts`."""
    source = (Path(settings.BASE_DIR) / "apps" / "registry" / "catastro.py").read_text(
        encoding="utf-8"
    )
    # Comments stripped: the one explaining *why* the literal is banned names it.
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    assert "TERMINAL_STATUSES" in code
    assert '"retired"' not in code


def test_an_explicit_status_filter_wins_over_the_terminal_exclusion(world, root):
    """Asking for "Retired" and being handed nothing would be a filter that
    lies. The exclusion is a default, not a rule."""
    catastro = build_catastro(root, CatastroFilters(status="retired"))

    assert _registrations(catastro) == ["RPA-0001"]


def test_archived_rows_are_out_unless_they_are_asked_for(world, root):
    assert "RPA-0002" not in _registrations(build_catastro(root))
    assert "Dario Luna" not in _names(build_catastro(root))

    included = build_catastro(root, CatastroFilters(include_archived=True))

    assert "RPA-0002" in _registrations(included)
    assert "Dario Luna" in _names(included)


# -- what the filters hide, said out loud -----------------------------------


def test_a_cost_center_filter_says_how_much_it_hides(world, root):
    """`cost_center` is nullable on both models, so filtering by faena drops
    everything unassigned without a word. The report counts it and says so."""
    catastro = build_catastro(root, CatastroFilters(cost_center=world["north"]))

    assert _registrations(catastro) == ["RPA-7126"]
    assert _names(catastro) == ["Ana Rivas"]
    totals = catastro["totals"]
    assert totals["aircraft_without_cost_center"] == 1  # RPA-9001
    assert totals["operators_without_cost_center"] == 1  # Carla Diaz
    assert totals["unassigned_are_hidden"] is True

    sentences = totals_sentence(catastro)
    assert len(sentences) == 2
    assert "1" in sentences[1]


def test_without_a_filter_the_unassigned_rows_are_on_the_page_and_counted(world, root):
    """Same two numbers, opposite meaning: here those rows *are* listed, so the
    sentence has to read "of these" and not "are not listed". Without the flag
    the two cases would print the same words about different facts."""
    catastro = build_catastro(root)

    totals = catastro["totals"]
    assert totals["aircraft_without_cost_center"] == 1
    assert totals["unassigned_are_hidden"] is False

    sentences = totals_sentence(catastro)
    assert len(sentences) == 2
    assert (
        sentences[1]
        != totals_sentence(
            build_catastro(root, CatastroFilters(cost_center=world["north"]))
        )[1]
    )


@pytest.mark.django_db
def test_a_single_row_reads_in_the_singular(root):
    """Lo encontró el padrón real el día que se desplegó: con una sola aeronave
    sin faena el informe decía **"1 aeronaves"**.

    Los dos conteos se interpolaban en un mensaje solo, y `ngettext` maneja uno.
    Ahora cada frase contada se arma aparte y la oración las compone. Ninguno de
    los fixtures anteriores lo habría cazado: todos tenían dos de cada cosa, que
    es el descuido que hace que un caso límite llegue a producción.
    """
    center = CostCenter.objects.create(code="CC001", name="Una sola")
    Aircraft.objects.create(
        registration="RPA-UNO",
        type="Multirotor",
        model="M",
        manufacturer="DJI",
        cost_center=center,
    )
    Operator.objects.create(full_name="Solo Uno", employee_id="E-1")

    first, second = totals_sentence(build_catastro(root))

    assert "1 aeronave " in first and "1 aeronaves" not in first
    assert "1 operador " in first and "1 operadores" not in first
    # El operador suelto es el que la segunda frase cuenta, también en singular.
    assert "1 operador " in second and "1 operadores" not in second
    # El verbo se queda en plural, y eso es correcto: dos sujetos unidos por "y"
    # llevan verbo plural en español.
    assert "no tienen" in second


@pytest.mark.django_db
def test_several_rows_read_in_the_plural(world, root):
    """La otra mitad del acuerdo, para que el arreglo no se pase de largo."""
    sentence = totals_sentence(build_catastro(root))[0]

    assert "3 aeronaves" in sentence
    assert "3 operadores" in sentence


@pytest.mark.django_db
def test_an_empty_roster_reads_in_the_plural_too(root):
    """Cero es plural en español ("0 aeronaves"), que es lo que la forma plural
    de gettext devuelve para `n != 1`."""
    sentence = totals_sentence(build_catastro(root))[0]

    assert "0 aeronaves" in sentence
    assert "0 operadores" in sentence


def test_a_roster_with_nothing_left_out_carries_no_dangling_clause(db, root):
    center = CostCenter.objects.create(code="CC730", name="Salares")
    Aircraft.objects.create(
        registration="RPA-1",
        type="t",
        model="m",
        manufacturer="DJI",
        cost_center=center,
    )
    Operator.objects.create(full_name="Solo", employee_id="E-9", cost_center=center)

    assert len(totals_sentence(build_catastro(root))) == 1


# -- rows ------------------------------------------------------------------


def test_the_rows_match_the_headers_and_blanks_print_a_dash(world, root):
    from .catastro import AIRCRAFT_HEADERS, OPERATOR_HEADERS

    catastro = build_catastro(root)
    fleet = aircraft_rows(catastro)
    personnel = operator_rows(catastro)

    assert all(len(row) == len(AIRCRAFT_HEADERS) for row in fleet)
    assert all(len(row) == len(OPERATOR_HEADERS) for row in personnel)

    loose = next(row for row in fleet if row[0] == "RPA-9001")
    # An empty cell reads as "we forgot to fill it in"; a dash reads as "there
    # is nothing there", which is the true statement.
    assert loose[4] == BLANK  # no serial number
    assert loose[5] == BLANK  # no year
    assert loose[7] == BLANK  # no cost center

    identified = next(row for row in fleet if row[0] == "RPA-7126")
    assert identified[4] == "1581F5FHC245"
    assert identified[7] == "CC738"
    # The status is the label, not the stored code: "retired" on a document
    # handed to a client is our database talking, not our operation.
    assert identified[6] != "active"


def test_the_operator_rows_carry_no_contact_details(world, root):
    """Deliberate scope: the user asked for the roster, not for a contact list,
    and this document is written to leave the building."""
    from .catastro import OPERATOR_HEADERS

    headers = [str(header).lower() for header in OPERATOR_HEADERS]

    assert not [header for header in headers if "mail" in header or "phone" in header]


# -- cost ------------------------------------------------------------------


def test_the_roster_costs_two_queries(world, root, django_assert_num_queries):
    """One per table. `select_related("cost_center")` is what keeps the code
    column from firing a query per row."""
    with django_assert_num_queries(2):
        catastro = build_catastro(root)
        aircraft_rows(catastro)
        operator_rows(catastro)


def test_a_cost_center_filter_costs_two_more_and_no_more(
    world, root, django_assert_num_queries
):
    """The two counts of what the filter hides cannot be done in Python -- those
    rows are outside the result set -- so they are two COUNTs, not a second
    fetch of the whole table."""
    with django_assert_num_queries(4):
        build_catastro(root, CatastroFilters(cost_center=world["north"]))


# -- tenancy ---------------------------------------------------------------


@pytest.mark.django_db
def test_another_tenants_rows_are_out_of_scope(world, root):
    other = OperationalTenant.objects.create(name="Otro", slug="otro")
    Aircraft.objects.create(
        registration="ZZZ-999",
        type="Multirotor",
        model="M",
        manufacturer="DJI",
        tenant=other,
    )
    Operator.objects.create(full_name="Zoe Ajena", employee_id="Z-1", tenant=other)
    member = User.objects.create_user("member", password="password")
    TenantMembership.objects.create(
        tenant=OperationalTenant.objects.get(slug="default"), user=member
    )

    catastro = build_catastro(member)

    assert "ZZZ-999" not in _registrations(catastro)
    assert "Zoe Ajena" not in _names(catastro)
    # A superuser sees every tenant, which is what `scope_queryset_to_tenant`
    # promises -- asserted so the test above cannot pass by over-filtering.
    assert "ZZZ-999" in _registrations(build_catastro(root))
