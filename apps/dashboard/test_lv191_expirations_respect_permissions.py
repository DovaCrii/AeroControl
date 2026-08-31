"""LV-191: la lista de vencimientos del panel respeta los permisos del usuario.

Encontrado el 2026-08-31, y **encontrado por el arreglo de `LV-187`**: al quitar
el guard que escondía el panel entero cuando la base parecía vacía, un test de
`LV-147` empezó a fallar con su propio nombre como diagnóstico —
`test_a_permit_the_user_may_not_see_leaks_nothing`— porque el folio del permiso
oculto aparecía en la lista de vencimientos, a un usuario que sólo tenía
`view_costcenter`.

El guard **no era un control de acceso** y estaba funcionando como uno: escondía
la sección completa mientras la base de un test estuviera vacía, así que dos
tests distintos pasaban por la razón equivocada. Retirarlo no creó la fuga, la
destapó — la lista nunca filtró por permisos, y en producción, donde la base no
está vacía, nunca la tapó nada.

Qué se filtraba: los cinco orígenes nombran su sujeto, y ése es justo el dato —
el folio de un permiso, la matrícula de una aeronave, **el nombre de una
persona** y su credencial DGAC, el título de un documento. El panel se abre en
cada inicio de sesión, así que lo veía todo el que pudiera entrar.

El gate va en un solo lugar (`add()`, dentro de `upcoming_expirations`) y sobre
una tabla declarada, `EXPIRATION_PERMISSIONS`: seis `if` repartidos por la
función son seis lugares donde olvidarse de uno, y un `if` olvidado acá no se ve.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.dashboard.views import EXPIRATION_PERMISSIONS, upcoming_expirations
from apps.operations.models import FlightPermission
from apps.registry.models import (
    Aircraft,
    CostCenter,
    KnowledgeAssessment,
    Operator,
    Qualification,
    QualificationType,
)

TODAY = timezone.localdate()
CUTOFF = TODAY + timedelta(days=30)
SOON = TODAY + timedelta(days=10)


@pytest.fixture
def everything(db):
    """Una fila de cada uno de los seis orígenes, todas dentro de la ventana."""
    center = CostCenter.objects.create(code="CC738", name="MLP")
    operator = Operator.objects.create(
        employee_id="E-1",
        full_name="Ana Rivas",
        cost_center=center,
        credential_expiry=SOON,
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-4025",
        serial_number="SN-1",
        cost_center=center,
        insurance_expiry=SOON,
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.create(code="MR", name="Multi"),
        expiry_date=SOON,
    )
    KnowledgeAssessment.objects.create(
        operator=operator,
        question_count=10,
        correct_count=9,
        score_percent=90,
        passed=True,
        expires_on=SOON,
    )
    permit = FlightPermission.objects.create(
        internal_folio="JEJ-2026-004",
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=SOON,
        location="Quebrada km 13",
        area_type="dan_91",
    )
    Document.objects.create(
        title="Carta Permiso",
        doc_type=DocumentType.objects.create(code="permit-letter", name="Carta"),
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        issue_date=TODAY - timedelta(days=1),
        expiry_date=SOON,
        is_current_version=True,
    )
    return {"aircraft": aircraft, "operator": operator, "permit": permit}


@pytest.mark.django_db
class TestWhatWasLeaking:
    def test_a_user_with_no_permissions_sees_no_rows(self, everything):
        """Seis vencimientos en la base y ninguno es asunto de este usuario."""
        assert upcoming_expirations(TODAY, CUTOFF, None, login_as().user) == []

    def test_the_permit_folio_does_not_reach_the_page(self, everything):
        """El caso exacto que `LV-147` dejó anotado en su nombre."""
        content = login_as("view_costcenter").get(reverse("dashboard")).content.decode()

        assert "JEJ-2026-004" not in content

    def test_a_persons_name_does_not_reach_the_page(self, everything):
        """El dato más sensible de la lista: una credencial DGAC por vencer va con
        el nombre de la persona."""
        content = login_as("view_costcenter").get(reverse("dashboard")).content.decode()

        assert "Ana Rivas" not in content

    def test_each_source_needs_its_own_permission(self, everything):
        """Uno por uno: tener el permiso de una fuente no muestra las otras.

        Recorre `EXPIRATION_PERMISSIONS`, así que **una fuente nueva sin entrada
        en la tabla hace fallar esto** en vez de entrar sin gate.
        """
        for permission in EXPIRATION_PERMISSIONS.values():
            codename = permission.split(".", 1)[1]
            user = login_as(codename).user

            items = upcoming_expirations(TODAY, CUTOFF, None, user)

            assert items, f"{codename} no muestra su propia fuente"
            # Con un solo permiso, todas las filas tienen que venir de esa
            # fuente: si aparece otra, el gate no aísla.
            kinds = {item["kind"] for item in items}
            assert len(kinds) == 1, f"{codename} trajo filas de otra fuente: {kinds}"


@pytest.mark.django_db
class TestWhatStillWorks:
    def test_a_superuser_sees_all_six(self, everything, client, django_user_model):
        """El contrapeso: el gate no puede esconderle nada a quien puede verlo
        todo, o el panel dejaría de servir para lo que existe."""
        django_user_model.objects.create_superuser("admin", "a@test.com", "password")
        assert client.login(username="admin", password="password")

        response = client.get(reverse("dashboard"))

        assert len(response.context["expirations"]) == 6

    def test_without_a_user_nothing_is_gated(self, everything):
        """`user=None` no gatea, a propósito: los llamadores internos y los tests
        que preguntan "qué vence" están probando la consulta, no la
        autorización. La vista pasa siempre `request.user`."""
        assert len(upcoming_expirations(TODAY, CUTOFF)) == 6

    def test_the_table_covers_every_source(self, everything):
        """Si una fuente entra a `upcoming_expirations` sin fila en la tabla, el
        `add()` levanta `KeyError` — falla ruidosamente en vez de colarse. Este
        test lo fija: las seis fuentes que la función produce están declaradas."""
        kinds = {item["kind"] for item in upcoming_expirations(TODAY, CUTOFF)}

        assert len(kinds) == len(EXPIRATION_PERMISSIONS) == 6
