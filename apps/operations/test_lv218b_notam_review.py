"""LV-218(b): que alguien revisó los NOTAM, en el expediente.

**Es la mitad de `LV-218` que no depende de la DGAC.** El paso (a) dejó el enlace
al IFIS en la ficha; el cruce automático espera saber si existe una fuente
estructurada (ver `docs/dev/lv218-consulta-notam-dgac.md`). Pero mostrar un
enlace no es evidencia: después del vuelo no había forma de contestar *"¿se
revisaron los avisos antes de volar, y qué decían?"*.

Lo que estos tests protegen, por orden de gravedad:

1. **Que "no afecta" no pueda escribirse por omisión.** Es el fallo silencioso
   que toda la fila viene evitando: una revisión guardada de apuro afirmando que
   ningún aviso afecta al vuelo.
2. **Que decir "afecta" obligue a decir cuál.** Un registro con la forma de una
   evidencia y sin su contenido es peor que ninguno.
3. **Que el renglón no le ponga un pendiente a cada borrador**, que es el daño
   que `LV-194` acaba de corregir en esta misma pantalla.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .models import FlightPermission, NotamReview


def _permit(status=None, **extra):
    centre = CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)
    today = timezone.localdate()
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status or FlightPermission.STATUS_APPROVED,
        permission_number="6551",
        location="Tranque el Mauro",
        area_type="unpopulated",
        valid_from=today,
        valid_until=today + timezone.timedelta(days=60),
        **extra,
    )


class TestTheAnswerCannotBeWrittenByOmission:
    @pytest.mark.django_db
    def test_the_outcome_has_no_default(self, db):
        """⚠️ **El punto de toda la clase.** Con un "no afecta" por omisión, una
        revisión registrada de apuro afirmaría que ningún aviso afecta al vuelo —
        exactamente el fallo silencioso que `LV-218` viene evitando desde que
        decidió entregar un enlace y no un resultado."""
        review = NotamReview(permission=_permit(), target_date=timezone.localdate())

        with pytest.raises(ValidationError):
            review.full_clean()

    @pytest.mark.django_db
    def test_saying_it_affects_requires_saying_which(self, db):
        """Mismo criterio que resolver una alerta (`R6.2`) o liberar un entregable
        bajo criterio (`R7.4`): la afirmación grave exige el motivo escrito."""
        review = NotamReview(
            permission=_permit(),
            target_date=timezone.localdate(),
            outcome=NotamReview.OUTCOME_AFFECTED,
            findings="",
        )

        with pytest.raises(ValidationError) as raised:
            review.full_clean()

        assert "findings" in raised.value.message_dict

    @pytest.mark.django_db
    def test_and_it_saves_when_it_does_say_which(self, db):
        review = NotamReview(
            permission=_permit(),
            target_date=timezone.localdate(),
            outcome=NotamReview.OUTCOME_AFFECTED,
            findings="A1234/26 cierra el sector norte entre 10:00 y 14:00 UTC.",
        )

        review.full_clean()
        review.save()

        assert NotamReview.objects.count() == 1

    @pytest.mark.django_db
    def test_nothing_published_needs_no_findings(self, db):
        """ "No hay avisos" es una respuesta completa por sí sola."""
        review = NotamReview(
            permission=_permit(),
            target_date=timezone.localdate(),
            outcome=NotamReview.OUTCOME_NONE,
        )

        review.full_clean()

    @pytest.mark.django_db
    def test_the_three_outcomes_are_distinct(self, db):
        """Tres estados y no un booleano: "no hay avisos publicados" y "hay
        avisos y ninguno afecta" se confunden en un `False`, y la diferencia
        importa — la segunda dice que alguien leyó y descartó."""
        assert len(NotamReview.OUTCOME_CHOICES) == 3


class TestRecordingIt:
    @pytest.mark.django_db
    def test_the_form_proposes_the_permit_date(self, db):
        """El día por el que se revisa es el del vuelo autorizado, y el permiso
        ya lo sabe. Queda editable: se puede revisar el lunes lo que se vuela el
        jueves."""
        permit = _permit()
        client = login_as("add_notamreview", "view_flightpermission")

        body = client.get(
            reverse("notam-review-create", args=[permit.pk])
        ).content.decode()

        assert f"{permit.valid_from:%Y-%m-%d}" in body

    @pytest.mark.django_db
    def test_the_official_link_is_on_the_page(self, db):
        """La pantalla no sirve para inventar una respuesta: sirve para dejar
        constancia de lo que se leyó **allá**. Sin el enlace a la vista, sería un
        formulario que invita a responder de memoria."""
        permit = _permit()
        client = login_as("add_notamreview", "view_flightpermission")

        body = client.get(
            reverse("notam-review-create", args=[permit.pk])
        ).content.decode()

        assert "notam" in body.lower()
        assert "aipchile" in body or "IFIS" in body

    @pytest.mark.django_db
    def test_it_records_who_and_freezes_the_query(self, db):
        """La consulta se guarda **tal como estaba**: si el aeródromo declarado
        del permiso cambia después, el expediente tiene que seguir diciendo qué
        se consultó de verdad."""
        permit = _permit()
        client = login_as("add_notamreview", "view_flightpermission")

        client.post(
            reverse("notam-review-create", args=[permit.pk]),
            {
                "target_date": f"{timezone.localdate():%Y-%m-%d}",
                "outcome": NotamReview.OUTCOME_NONE,
                "findings": "",
            },
        )

        review = NotamReview.objects.get()
        assert review.permission == permit
        assert review.reviewed_by is not None
        assert review.consulted_url == (permit.notam_url or "")

    @pytest.mark.django_db
    def test_an_invalid_answer_redraws_instead_of_saving(self, db):
        permit = _permit()
        client = login_as("add_notamreview", "view_flightpermission")

        response = client.post(
            reverse("notam-review-create", args=[permit.pk]),
            {
                "target_date": f"{timezone.localdate():%Y-%m-%d}",
                "outcome": NotamReview.OUTCOME_AFFECTED,
                "findings": "",
            },
        )

        assert response.status_code == 200
        assert not NotamReview.objects.exists()

    @pytest.mark.django_db
    def test_it_needs_the_add_permission(self, db):
        permit = _permit()
        client = login_as("view_flightpermission")

        response = client.post(
            reverse("notam-review-create", args=[permit.pk]),
            {
                "target_date": f"{timezone.localdate():%Y-%m-%d}",
                "outcome": NotamReview.OUTCOME_NONE,
            },
        )

        assert response.status_code in (302, 403)
        assert not NotamReview.objects.exists()

    @pytest.mark.django_db
    def test_the_role_that_flies_can_record_it(self, db):
        """`bootstrap_roles` tiene que otorgarlo, o la función existe y nadie la
        alcanza — el defecto que `R3` pagó con los permisos de `ReportRun`."""
        from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS

        assert "add_notamreview" in ROLE_PERMISSIONS["Operations"]
        # Append-only: se otorgan `add` y `view`, nunca `change`.
        assert "change_notamreview" not in ROLE_PERMISSIONS["Operations"]
        # Cumplimiento la audita, no la produce: no es quien vuela.
        assert "view_notamreview" in ROLE_PERMISSIONS["Compliance"]
        assert "add_notamreview" not in ROLE_PERMISSIONS["Compliance"]


class TestTheDossierRow:
    @pytest.mark.django_db
    def test_an_approved_permit_without_a_review_offers_to_record_it(self, db):
        from .dossier import operational_dossier

        permit = _permit()
        rows = {row.key: row for row in operational_dossier(permit)["items"]}

        assert "notam" in rows
        assert rows["notam"].status != "ok"

    @pytest.mark.django_db
    def test_a_requested_permit_has_no_row_at_all(self, db):
        """⚠️ **La decisión del renglón.** Un permiso solicitado no autoriza a
        volar, así que no hay nada que revisar: dibujarle un renglón ámbar le
        pondría un pendiente a cada borrador, y ese es el daño que `LV-194` acaba
        de corregir en esta misma pantalla — un contador que no puede llegar a
        cero enseña a ignorar el contador."""
        from .dossier import operational_dossier

        permit = _permit(status=FlightPermission.STATUS_REQUESTED)
        rows = {row.key: row for row in operational_dossier(permit)["items"]}

        assert "notam" not in rows

    @pytest.mark.django_db
    def test_a_recorded_review_closes_the_row_and_says_what_it_found(self, db):
        """ "Se revisó" con un aviso que afecta y sin decirlo sería peor que no
        haber revisado, porque parece resuelto."""
        from .dossier import operational_dossier

        permit = _permit()
        NotamReview.objects.create(
            permission=permit,
            target_date=timezone.localdate(),
            outcome=NotamReview.OUTCOME_AFFECTED,
            findings="A1234/26 cierra el sector norte.",
        )

        rows = {row.key: row for row in operational_dossier(permit)["items"]}

        assert rows["notam"].status == "ok"
        assert "afecta" in rows["notam"].detail.lower() or (
            "affects" in rows["notam"].detail.lower()
        )
