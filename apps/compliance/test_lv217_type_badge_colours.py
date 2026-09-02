"""LV-217: color en la píldora del tipo, sin canibalizar la urgencia.

Pedido del usuario con captura: *"a los vencimientos y alertas poner colores para
diferenciar los tag de qué es cada uno; hoy no tiene y es gris"*, y en un segundo
mensaje: *"lo mismo en alerta, el tipo de entidad"*.

Los cinco orígenes de la lista de vencimientos llevaban el mismo
`bg-secondary-subtle`, y la columna "Tipo de entidad" de la bandeja también: había
que leer el texto de cada píldora para saber de qué hablaba la fila — justo lo que
una píldora de color existe para evitar.

**Lo que estos tests protegen no es el color, es que las dos escalas no choquen.**
La urgencia (`LV-148`) ya usa color en la misma fila, y un tipo compitiendo por el
mismo canal es cómo se pierde el rojo.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.digest import BUCKET_BADGE_CSS, ENTITY_TONES, SUBJECT_TONE_CSS


class TestTheTwoScalesDoNotCollide:
    def test_no_type_tone_uses_an_urgency_colour(self):
        """`danger`, `warning` e `info` son de la urgencia y de nadie más.

        Es la única regla dura de esta fila: si un tipo se pinta de rojo o ámbar,
        la fila tiene dos señales gritando y la que importa deja de destacar.
        """
        urgency_colours = {"danger", "warning", "info"}

        for tone, css in SUBJECT_TONE_CSS.items():
            for colour in urgency_colours:
                assert colour not in css, (
                    f"el tono '{tone}' usa '{colour}', que pertenece a la escala "
                    "de urgencia de LV-148"
                )

    def test_the_urgency_scale_owns_its_own_levels(self):
        """La guarda por el otro lado: que la urgencia siga teniendo escala propia.

        **Renombrado y reorientado en `UX-01`.** Se llamaba
        `test_the_urgency_scale_still_owns_those_colours` y comprobaba que las
        tablas de urgencia contuvieran las palabras `danger` y `warning` — o sea,
        se apoyaba en los nombres de las utilidades de Bootstrap. Desde `UX-01` la
        urgencia se escribe con tokens de severidad (`sev-critical`…), así que la
        afirmación correcta es que **tiene sus cinco niveles y ninguno se solapa
        con los tonos de tipo**, que es lo que este archivo protege.
        """
        niveles = {css.removeprefix("sev-") for css in BUCKET_BADGE_CSS.values()}

        assert niveles == {"critical", "warning", "caution", "advisory", "nominal"}
        # Y el punto de siempre: los tonos de tipo no invaden esa escala.
        for css in SUBJECT_TONE_CSS.values():
            assert "sev-" not in css

    def test_three_tones_are_bootstrap_pairs_and_one_is_ours(self):
        """Tres pares de Bootstrap y un color propio, **por medición**.

        La primera versión de este test exigía que los cuatro fueran pares
        `-subtle`/`-emphasis`, y era la intención del diseño: Bootstrap ya
        contrasta esos pares en los dos temas y ahorra medir ocho combinaciones.
        Pero de sus ocho familias, tres están reservadas a la urgencia y de las
        cinco restantes sólo **dos** son cromáticas — las otras tres son grises
        que, medidos en el navegador, quedaban a once puntos de canal unos de
        otros. Con cuatro tipos conviviendo en la misma lista, el cuarto color
        hubo que definirlo.

        El test sigue igual de estricto por el otro lado: el que no viene de
        Bootstrap tiene que tener su regla en la hoja **y** su variante de tema
        oscuro, o la píldora quedaría sin fondo en uno de los dos temas.
        """
        from pathlib import Path

        propios = []
        for tone, css in SUBJECT_TONE_CSS.items():
            if "-subtle" in css:
                assert "-emphasis" in css, tone
            else:
                propios.append((tone, css))

        assert len(propios) == 1, propios
        _tone, clase = propios[0]
        hoja = Path("static/css/app.css").read_text(encoding="utf-8")
        assert f".{clase} {{" in hoja
        assert f'[data-theme="dark"] .{clase} {{' in hoja

    def test_the_tones_are_distinguishable_from_each_other(self):
        """Cuatro tonos, cuatro valores: ninguno repetido.

        Compara las cadenas completas y no la "familia" extraída del nombre: el
        tono propio no lleva `bg-`, y la versión anterior lo partía con
        `split("bg-")[1]` y reventaba con `IndexError` — un test que falla por su
        propio parser no dice nada del defecto que vigila.
        """
        valores = list(SUBJECT_TONE_CSS.values())

        assert len(valores) == len(set(valores)), valores


class TestTheDashboardListIsColoured:
    @pytest.mark.django_db
    def test_each_source_carries_its_own_tone(self, db):
        from apps.dashboard.views import (
            EXPIRATION_PERMISSIONS,
            EXPIRATION_SUBJECT_TONES,
        )

        # **Las dos tablas tienen que cubrir lo mismo.** Agregar una fuente y
        # olvidar el color es el defecto que esta fila vino a arreglar, así que la
        # guarda es que las claves coincidan exactamente.
        assert set(EXPIRATION_SUBJECT_TONES) == set(EXPIRATION_PERMISSIONS)

    @pytest.mark.django_db
    def test_a_permit_and_a_document_do_not_share_a_colour(self, db):
        """Son los dos orígenes que más aparecen juntos en la lista."""
        assert SUBJECT_TONE_CSS["permit"] != SUBJECT_TONE_CSS["document"]

    @pytest.mark.django_db
    def test_the_expiring_permit_row_gets_the_permit_tone(self, db):
        from apps.dashboard.views import upcoming_expirations
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        today = timezone.localdate()
        cc = CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)
        FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            location="Site",
            area_type="unpopulated",
            valid_from=today - timedelta(days=60),
            valid_until=today + timedelta(days=10),
        )

        rows = upcoming_expirations(today, today + timedelta(days=30))

        assert rows
        assert rows[0]["kind_css"] == SUBJECT_TONE_CSS["permit"]

    @pytest.mark.django_db
    def test_a_missing_tone_is_not_silently_grey(self, db):
        """En el panel las fuentes están codificadas: un olvido debe levantar.

        `add()` busca la clave sin `get`, así que agregar una fuente sin su tono
        falla en el momento en vez de dibujarse gris para siempre — el estado que
        el usuario reportó y que nadie reportaría dos veces.
        """
        from apps.dashboard import views

        assert (
            "EXPIRATION_SUBJECT_TONES[model]"
            in open(views.__file__, encoding="utf-8").read()
        )


class TestTheAlertInboxIsColoured:
    @pytest.mark.django_db
    def test_the_entity_badge_reads_from_the_shared_table(self, db):
        """Una sola tabla para las dos pantallas.

        Con dos, una se desincroniza: es lo que pasó con la escala de urgencia
        antes de `LV-148`, ámbar en el panel y azul en la bandeja.
        """
        from apps.compliance.models import Alert, AlertRule
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        cc = CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
        )
        rule = AlertRule.objects.create(
            name="R",
            entity_type="operations.flightpermission",
            field_to_watch="valid_until",
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(FlightPermission),
            object_id=permit.pk,
            message="x",
        )

        assert alert.entity_tone_css == SUBJECT_TONE_CSS["permit"]

    @pytest.mark.django_db
    def test_an_unknown_model_falls_back_to_grey_instead_of_failing(self, db):
        """Acá el fallback **sí** corresponde, al revés que en el panel.

        Las reglas las configura el usuario, así que puede haber una sobre un
        modelo que la tabla no conozca. Una bandeja que revienta por un color es
        peor que una píldora sin color.
        """
        from apps.compliance.models import Alert, AlertRule, DocumentType

        # Un modelo real que la tabla no lista.
        rule = AlertRule.objects.create(
            name="R2", entity_type="compliance.documenttype", field_to_watch="name"
        )
        doc_type = DocumentType.objects.create(code="x", name="X")
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(DocumentType),
            object_id=doc_type.pk,
            message="x",
        )

        assert alert.entity_tone_css == SUBJECT_TONE_CSS["document"]

    def test_every_watchable_model_of_the_seeded_rules_has_a_tone(self):
        """Las reglas que el repo siembra sí deben estar todas cubiertas.

        El fallback existe para lo que el usuario configure a mano, no para
        ahorrarse las entradas de lo que la app instala por su cuenta.
        """
        from apps.compliance.management.commands.seed_alert_rules import (
            ESSENTIAL_RULES,
            OPTIONAL_RULES,
        )

        for _name, entity_type, _field, _days in ESSENTIAL_RULES + OPTIONAL_RULES:
            assert entity_type in ENTITY_TONES, entity_type
