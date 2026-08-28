"""LV-173: un intento de la prueba se retira archivándolo, nunca borrándolo.

Pedido del usuario: que root pueda sacar un intento. **Lo que no se hace es
borrarlo**, y hay dos razones encima de la otra. `AGENTS.md` prohíbe borrar filas
operativas; y `registry.knowledgeassessment` está en `WATCHABLE_MODELS`, así que
un intento aprobado **alimenta el motor de vencimientos** — y `generate_alerts`
filtra `is_active=True`. Verificado en el código, no supuesto: retirar el intento
que sostiene la vigencia le apaga la alerta a esa persona y le cambia el estado
de cumplimiento **sin que ninguna pantalla lo diga**.

Por eso lo que se prueba acá no es "el botón archiva" sino las cuatro cosas que
hacen que archivar sea seguro:

- **Se avisa antes, y sólo cuando hay algo que avisar.** Si al archivar la
  persona se queda sin prueba vigente, aparece la confirmación con su nombre. Un
  intento insuficiente, uno vencido o uno que otro posterior ya reemplazó se
  archiva directo: advertir ahí sería ruido, y el ruido enseña a no leer.
- **La fila sobrevive.** Archivar cambia `is_active`, no borra.
- **Queda a la vista y se puede volver atrás.** Un intento retirado que
  desaparece es indistinguible de uno borrado.
- **Queda en la auditoría.** Es la mitad que convierte "se fue" en "lo sacó
  alguien, tal día".
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.registry.models import KnowledgeAssessment, Operator

TODAY = timezone.localdate()


def _attempt(operator, *, passed=True, months=12, **kwargs):
    return KnowledgeAssessment.objects.create(
        operator=operator,
        question_count=25,
        correct_count=25 if passed else 10,
        score_percent=100 if passed else 40,
        passed=passed,
        expires_on=TODAY + timezone.timedelta(days=30 * months)
        if months
        else TODAY - timezone.timedelta(days=1),
        **kwargs,
    )


@pytest.fixture
def operator(db):
    return Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")


def test_archiving_the_only_valid_attempt_asks_first(operator):
    """Es el caso en que el estado de cumplimiento cambia sin avisar a nadie."""
    attempt = _attempt(operator)
    client = login_as("delete_knowledgeassessment", "view_operator")

    response = client.post(reverse("assessment-archive", args=[attempt.pk]))

    assert response.status_code == 200
    assert "Ana Rivas" in response.content.decode()
    attempt.refresh_from_db()
    assert attempt.is_active, "no se archiva antes de confirmar"


def test_confirming_archives_it(operator):
    attempt = _attempt(operator)
    client = login_as("delete_knowledgeassessment", "view_operator")

    response = client.post(
        reverse("assessment-archive", args=[attempt.pk]), {"confirm": "1"}
    )

    attempt.refresh_from_db()
    assert not attempt.is_active
    assert response.status_code == 302
    assert response.url == reverse("operator-detail", args=[operator.pk])


def test_the_row_survives_archiving(operator):
    """Archivar no es borrar: la fila sigue ahí, con su copia de lo preguntado."""
    attempt = _attempt(operator)
    client = login_as("delete_knowledgeassessment", "view_operator")

    client.post(reverse("assessment-archive", args=[attempt.pk]), {"confirm": "1"})

    assert KnowledgeAssessment.objects.filter(pk=attempt.pk).exists()


def test_an_insufficient_attempt_is_archived_without_asking(operator):
    """No sostiene ninguna vigencia, así que no hay nada que advertir."""
    attempt = _attempt(operator, passed=False)
    client = login_as("delete_knowledgeassessment", "view_operator")

    response = client.post(reverse("assessment-archive", args=[attempt.pk]))

    attempt.refresh_from_db()
    assert response.status_code == 302
    assert not attempt.is_active


def test_an_expired_attempt_is_archived_without_asking(operator):
    """Ya no sostenía la vigencia antes de tocarlo."""
    attempt = _attempt(operator, months=0)
    client = login_as("delete_knowledgeassessment", "view_operator")

    response = client.post(reverse("assessment-archive", args=[attempt.pk]))

    attempt.refresh_from_db()
    assert response.status_code == 302
    assert not attempt.is_active


def test_a_superseded_attempt_is_archived_without_asking(operator):
    """Con otro aprobado y vigente, archivar éste no cambia el estado de nadie."""
    older = _attempt(operator)
    _attempt(operator)
    client = login_as("delete_knowledgeassessment", "view_operator")

    response = client.post(reverse("assessment-archive", args=[older.pk]))

    older.refresh_from_db()
    assert response.status_code == 302, (
        "advertir acá sería ruido, y el ruido enseña a no leer"
    )
    assert not older.is_active


def test_archiving_is_written_to_the_audit_trail(operator):
    attempt = _attempt(operator)
    client = login_as("delete_knowledgeassessment", "view_operator")

    client.post(reverse("assessment-archive", args=[attempt.pk]), {"confirm": "1"})

    assert AuditEvent.objects.filter(
        object_id=str(attempt.pk), action="archived"
    ).exists()


def test_an_archived_attempt_can_be_restored(operator):
    attempt = _attempt(operator)
    attempt.is_active = False
    attempt.save(update_fields=["is_active"])
    client = login_as("change_knowledgeassessment", "view_operator")

    response = client.post(reverse("assessment-restore", args=[attempt.pk]))

    attempt.refresh_from_db()
    assert attempt.is_active
    assert response.url == reverse("operator-detail", args=[operator.pk])


def test_the_file_shows_the_archived_ones_apart(operator):
    """Esconderlos los volvería indistinguibles de un borrado."""
    active = _attempt(operator)
    archived = _attempt(operator)
    archived.is_active = False
    archived.save(update_fields=["is_active"])
    client = login_as(
        "view_operator", "view_knowledgeassessment", "delete_knowledgeassessment"
    )

    body = client.get(reverse("operator-detail", args=[operator.pk])).content.decode()

    assert reverse("assessment-restore", args=[archived.pk]) in body
    assert reverse("assessment-archive", args=[active.pk]) in body


def test_without_the_delete_permission_there_is_no_archive_button(operator):
    _attempt(operator)
    client = login_as("view_operator", "view_knowledgeassessment")

    body = client.get(reverse("operator-detail", args=[operator.pk])).content.decode()

    assert "assessment-archive" not in body
    assert "/archive/" not in body


def test_nobody_archives_without_the_permission(operator):
    attempt = _attempt(operator)
    client = login_as("view_operator", "view_knowledgeassessment")

    response = client.post(
        reverse("assessment-archive", args=[attempt.pk]), {"confirm": "1"}
    )

    attempt.refresh_from_db()
    assert response.status_code == 403
    assert attempt.is_active
