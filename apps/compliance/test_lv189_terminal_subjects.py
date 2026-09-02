"""`LV-189`: un registro que terminó no es cumplimiento pendiente de nadie.

`_subject_scope` excluía los sujetos **archivados** y no los que están en estado
**terminal**, que son cosas distintas: una aeronave `retired` sigue
`is_active=True`. Así que sus documentos contaban en el cumplimiento de la
faena, y desde que `LV-188` ensanchó la tabla contaban también las cartas de
permisos caducados y denegados.

Es la misma regla que `LV-120` y `LV-83` ya aplicaron al cerrar permisos por
fecha, y la que `fleet_availability` aplica excluyendo `retired` del
denominador: **contar lo que terminó hace que el porcentaje baje para siempre
por una decisión correcta.**

⚠️ **Estos tests mueven cifras del informe**, igual que `LV-188`. Lo que fijan
no es un número sino el criterio, y el caso que lo separa de lo archivado es el
primero: un sujeto terminal **no** está archivado.
"""

from datetime import date, timedelta

import pytest
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.compliance.reports import (
    ALERT_COST_CENTER_PATHS,
    documents_for_cost_center,
)
from apps.compliance.watchables import terminal_statuses
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def doc_type(db):
    return DocumentType.objects.create(code="t", name="Tipo")


def _document(subject, doc_type, title):
    return Document.objects.create(
        title=title,
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        issue_date=date(2026, 1, 1),
        expiry_date=date(2027, 1, 1),
        is_current_version=True,
    )


class TestATerminalSubjectStopsCounting:
    @pytest.mark.django_db
    def test_a_retired_aircraft_is_not_archived_and_still_stops_counting(
        self, site, doc_type
    ):
        """**El caso que separa lo terminal de lo archivado.**

        `retired` deja la fila con `is_active=True`, así que el filtro que ya
        había no la tocaba. Ésa es toda la fila: dos criterios distintos que se
        parecían lo suficiente como para que uno pasara por el otro.
        """
        flying = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M3E",
            manufacturer="DJI",
            cost_center=site,
        )
        retired = Aircraft.objects.create(
            registration="RPA-2",
            type="RPA",
            model="M3E",
            manufacturer="DJI",
            cost_center=site,
            status="retired",
        )
        assert retired.is_active, "si esto falla, el test mide lo archivado"
        _document(flying, doc_type, "Del que vuela")
        _document(retired, doc_type, "Del retirado")

        names = set(documents_for_cost_center(site).values_list("title", flat=True))

        assert names == {"Del que vuela"}

    @pytest.mark.django_db
    def test_a_lapsed_permit_stops_counting_its_letters(self, site, doc_type):
        """Lo que `LV-188` sumó a la cuenta, y por lo que esta fila existe.

        Antes de `LV-188` los documentos colgados de un permiso no contaban en
        ninguna faena; al arreglarlo entraron **todos**, incluidos los de los
        permisos que ya terminaron.
        """
        today = timezone.localdate()
        live = FlightPermission.objects.create(
            cost_center=site,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            location="Sitio",
            area_type="unpopulated",
            valid_from=today - timedelta(days=10),
            valid_until=today + timedelta(days=10),
        )
        closed = FlightPermission.objects.create(
            cost_center=site,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_EXPIRED,
            permission_number="P-2",
            location="Sitio",
            area_type="unpopulated",
        )
        _document(live, doc_type, "Carta viva")
        _document(closed, doc_type, "Carta caducada")

        names = set(documents_for_cost_center(site).values_list("title", flat=True))

        assert names == {"Carta viva"}

    @pytest.mark.django_db
    def test_the_alerts_of_a_terminal_subject_still_belong_to_their_site(
        self, site, doc_type
    ):
        """**El filtro va sólo en la rama de documentos.**

        Una alerta se **atribuye**, no se cuenta: sigue perteneciendo a su faena
        aunque el registro haya terminado. Es el mismo reparto que `only_active`
        ya hacía, y meter lo terminal en las dos ramas habría borrado alertas de
        la vista por faena.
        """
        from apps.compliance.reports import _subject_scope

        retired = Aircraft.objects.create(
            registration="RPA-9",
            type="RPA",
            model="M3E",
            manufacturer="DJI",
            cost_center=site,
            status="retired",
        )
        _document(retired, doc_type, "Del retirado")

        # Se afirma sobre el **resultado** de cada rama y no sobre el `Q`: su
        # `str()` muestra el repr de la subconsulta, no el SQL, así que un test
        # que buscara "retired" en el texto pasaría o fallaría por cómo Django
        # imprime un objeto. Comprobado: fue el primer intento.
        attributed = Document.objects.filter(_subject_scope(site, only_active=False))
        counted = Document.objects.filter(_subject_scope(site, only_active=True))

        assert "Del retirado" in set(attributed.values_list("title", flat=True))
        assert "Del retirado" not in set(counted.values_list("title", flat=True))

    @pytest.mark.django_db
    def test_a_model_without_a_status_field_does_not_raise(self, site, doc_type):
        """Cuatro de los diez modelos de la tabla no tienen `status`.

        Un `exclude(status__in=())` a ciegas sobre ellos es un `FieldError`, y
        era el riesgo que la fila anotaba. Se comprueba recorriendo de verdad.
        """
        from apps.registry.models import Operator

        person = Operator.objects.create(
            employee_id="P1", full_name="Alguien", cost_center=site
        )
        _document(person, doc_type, "Del operador")

        names = set(documents_for_cost_center(site).values_list("title", flat=True))

        assert names == {"Del operador"}

    @pytest.mark.django_db
    def test_it_is_still_one_query(self, site, django_assert_num_queries):
        """El informe llama a esto **una vez por faena**, así que el `exclude`
        tiene que ir dentro de la subconsulta y no en un bucle de Python."""
        with django_assert_num_queries(1):
            list(documents_for_cost_center(site))


class TestEveryWatchedModelHasDecidedItsTerminalStatuses:
    """El guardián que el docstring de `terminal_statuses` prometía y **no
    existía**.

    Ese docstring dice que `test_watchable_models_declare_their_terminal_statuses`
    *"es lo que impide que el conjunto vacío signifique en silencio 'nadie se
    puso a hacerlo'"*. Ese test no está en el árbol — comprobado al escribir
    `LV-189`. Sin él, un modelo con `status` y sin `TERMINAL_STATUSES` queda
    fuera del filtro sin que nada lo diga, que es exactamente el modo de fallo
    que el conjunto vacío tiene.

    La expectativa se escribe a mano **a propósito**: derivarla del propio
    modelo sería tautológica. Un modelo nuevo obliga a agregar su fila acá, o
    sea a **decidir**.
    """

    EXPECTED = {
        "compliance.monthlycompliancereview": {"completed", "non_compliant"},
        "maintenance.maintenancerecord": {"completed"},
        "operations.flightpermission": {"completed", "denied", "expired"},
        "operations.flightrequest": {"closed"},
        "registry.aircraft": {"retired"},
        # ⚠️ **Vacío y correcto, no un olvido.** `GeoPlan` tiene `status` con
        # `rejected`, pero de ahí se sale con "Reanudar edición"
        # (`PLAN_TRANSITIONS`): un plan rechazado es trabajo que **volvió**, no
        # trabajo que terminó. Su `STATUS_BLOCKED` contesta otra pregunta —dónde
        # se detiene el flujo—, y confundirla con lo terminal habría sacado del
        # cumplimiento los documentos de planes vivos.
        "geo.geoplan": set(),
        # Sin campo `status`: nada que declarar.
        "registry.costcenter": set(),
        "registry.knowledgeassessment": set(),
        "registry.operator": set(),
        "registry.qualification": set(),
    }

    def test_the_declared_sets_are_the_ones_decided(self):
        for label, expected in self.EXPECTED.items():
            model = apps.get_model(label)
            assert terminal_statuses(model) == expected, label

    def test_no_watched_model_is_missing_from_the_decision(self):
        """Un modelo nuevo en la tabla cae acá y obliga a decidir.

        Es el mismo patrón que `test_every_declared_model_survives_the_filter`
        de `LV-188`: la lista escrita a mano es el mecanismo, no el descuido.
        """
        assert set(ALERT_COST_CENTER_PATHS) == set(self.EXPECTED)

    def test_a_model_with_a_status_field_and_no_declaration_is_deliberate(self):
        """Y si alguno queda vacío teniendo `status`, que sea porque se decidió.

        Hoy el único es `geo.geoplan`. Si aparece otro, este test lo nombra en
        el fallo en vez de dejar que pase de largo.
        """
        undeclared = {
            label
            for label in ALERT_COST_CENTER_PATHS
            if any(f.name == "status" for f in apps.get_model(label)._meta.get_fields())
            and not terminal_statuses(apps.get_model(label))
        }

        assert undeclared == {"geo.geoplan"}, (
            "un modelo con `status` dejó de declarar sus estados terminales, o "
            "apareció uno nuevo: decidilo y anotalo en EXPECTED"
        )
