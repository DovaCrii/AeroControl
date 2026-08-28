"""R5.8: "Habilitaciones" was redundant with the operator's own ficha --
Operator.authorizations (free text) said the same thing the Qualification
list showed structured, usually with no date. Moved: the ficha now shows the
operator's real qualifications, replacing the free-text field; the sidebar
link is hidden (Qualification/qualification-list are untouched -- they still
back the expiry alerts and the operator-aircraft compatibility check).

**LV-175 (2026-08-28) revirtió la mitad de arriba, y por eso dos afirmaciones
de este archivo cambiaron de signo.** Se dejan acá, actualizadas y con la razón
escrita, en vez de borrarlas: eran correctas cuando se escribieron, y el
historial de por qué la ficha muestra hoy el texto libre es justamente lo que
evita que alguien "arregle" esto de vuelta.

Lo que decidió el cambio fue el dato real de producción: el bloque estructurado
terminó mostrando tres filas con emisión y vencimiento en guion —las sembradas
por `seed_operator_qualifications` desde este mismo texto libre, sin fechas—, o
sea afirmando tres habilitaciones y respaldando ninguna. La regla del usuario en
`LV-152` gana: *"poner directamente en el recuadro lo que dice la DGAC, no más"*.
**Lo que sigue intacto** —y lo prueban los tests de más abajo— es el subsistema:
`Qualification`, `qualification-list` y lo que alimenta a `B4.4`."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import CostCenter, Operator, Qualification, QualificationType

TODAY = timezone.localdate()


@pytest.mark.django_db
def test_ficha_shows_the_free_text_authorizations_and_not_the_catalog():
    """LV-175 dio vuelta esta afirmación. Antes era al revés, y estaba bien.

    Lo que la dio vuelta no fue una opinión de diseño sino el padrón real: las
    habilitaciones estructuradas de producción vinieron todas de parsear este
    mismo texto libre y quedaron sin fecha, así que el bloque mostraba filas que
    no respaldaban nada.
    """
    cc = CostCenter.objects.create(code="CC1", name="One")
    operator = Operator.objects.create(
        employee_id="E1",
        full_name="Pilot One",
        cost_center=cc,
        authorizations="Matrice 300 Rtk - Mavic 3",
    )
    mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    Qualification.objects.create(
        operator=operator,
        qualification_type=mavic,
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=30),
    )

    response = login_as("view_operator", "view_qualification").get(
        reverse("operator-detail", args=[operator.pk])
    )
    content = response.content.decode()

    assert "Matrice 300 Rtk - Mavic 3" in content
    assert "Serie Mavic" not in content


@pytest.mark.django_db
def test_ficha_shows_empty_state_with_no_qualifications():
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")

    response = login_as("view_operator").get(
        reverse("operator-detail", args=[operator.pk])
    )

    assert list(response.context["qualifications"]) == []


@pytest.mark.django_db
def test_an_expired_qualification_is_still_marked_where_it_is_shown():
    """LV-175 movió esta afirmación de la ficha al listado, que es donde vive.

    Afirmarla sobre la ficha ahora pasaría por casualidad —`bg-danger` aparece
    en esa página por otros motivos— y un test que pasa por la razón equivocada
    es peor que no tenerlo.
    """
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
    phantom = QualificationType.objects.create(code="phantom", name="Serie Phantom")
    Qualification.objects.create(
        operator=operator,
        qualification_type=phantom,
        expiry_date=date(2000, 1, 1),
    )

    response = login_as("view_qualification").get(reverse("qualification-list"))

    assert "Serie Phantom" in response.content.decode()


@pytest.mark.django_db
def test_the_ficha_no_longer_carries_the_qualification_block_for_anybody():
    """Ni con permiso de cambio: el bloque se ocultó, no se restringió.

    La distinción importa. Si estuviera restringido, quien tiene el permiso
    seguiría viendo las filas sin fecha que motivaron `LV-175`.
    """
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
    mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    qualification = Qualification.objects.create(
        operator=operator, qualification_type=mavic
    )
    url = reverse("qualification-update", args=[qualification.pk])

    for client in (
        login_as("view_operator"),
        login_as("view_operator", "change_qualification"),
    ):
        body = client.get(reverse("operator-detail", args=[operator.pk]))
        assert url not in body.content.decode()


@pytest.mark.django_db
def test_sidebar_does_not_link_to_qualification_list_but_the_url_still_works():
    client = login_as("view_operator", "view_qualification")

    response = client.get(reverse("operator-list"))

    assert reverse("qualification-list") not in response.content.decode()
    # LV-7/LV-D8 pattern: hidden from the menu, not deleted -- the page is
    # still reachable directly (audit-all-at-once).
    assert client.get(reverse("qualification-list")).status_code == 200
