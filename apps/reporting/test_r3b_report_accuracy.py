"""Bloque 3: la exactitud del informe — el corte temporal y "sin fecha vs vencida".

Las dos brechas salieron de **usar** el informe, no de leerlo, y las dos son de
exactitud en un documento que va firmado a la autoridad:

1. **El padrón que se contaba era el de hoy.** `panel_readiness` recibía la
   fecha de corte y la usaba sólo para comparar vencimientos; la población salía
   de `filter(is_active=True)`, o sea el estado **actual**. Medido en
   producción: el payload de agosto devolvía 42 operadores y el informe emitido
   decía 41. Un informe de agosto generado en diciembre habría dado otra cifra —
   justo lo que congelar el dato viene a evitar.
2. **"Sin fecha" y "vencida" iban sumadas.** Los 8 sin credencial vigente del
   informe emitido eran 7 sin fecha más 1 vencida, y se arreglan distinto.

⚠️ **El límite del corte, que estos tests fijan explícitamente**: no reconstruye
el padrón de esa fecha, sólo deja de contar lo que todavía no existía. Sin
historial de `is_active` no hay más, y un test que afirmara lo contrario estaría
prometiendo una precisión que la base no tiene.
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.dashboard.views import panel_readiness
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.builder import build


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


def _cards(today, cost_center=None):
    return {c["key"]: c for c in panel_readiness(today, cost_center)["readiness"]}


def _born(instance, when):
    """Mueve el `created_at` de una fila ya guardada.

    `auto_now_add` sella la fecha al crear y no acepta que se la pasen, así que
    para simular un padrón que creció hay que actualizarla después. Se hace con
    `update()` —que no vuelve a pasar por `save()`— para que `auto_now` de
    `updated_at` no la pise.
    """
    type(instance).objects.filter(pk=instance.pk).update(created_at=when)


# El corte de estos tests es agosto de 2026, así que **toda fila que deba
# contarse hay que envejecerla**: creada hoy, el corte la deja fuera con razón.
# Es la advertencia de `LV-223` en su forma útil — una ventana fija obliga a
# fijar también la fecha del dato, y acá el propio arreglo la hace obligatoria.
PERIOD = date(2026, 8, 1)
CUTOFF = date(2026, 8, 31)


def _existed_in_july(*instances):
    for instance in instances:
        _born(instance, timezone.make_aware(timezone.datetime(2026, 7, 15, 12, 0)))


class TestTheRosterIsTheOneThatExistedAtTheCutoff:
    @pytest.mark.django_db
    def test_an_operator_loaded_after_the_cutoff_is_not_counted(self, site):
        """**La prueba del 42 contra el 41.**

        Sin esto, cada ficha que se carga en septiembre engorda el informe de
        agosto que ya se emitió, y el documento deja de coincidir con la copia
        que tiene la DGAC.
        """
        cutoff = timezone.localdate() - timedelta(days=40)
        before = Operator.objects.create(
            employee_id="P1", full_name="Ya estaba", cost_center=site
        )
        _born(before, timezone.now() - timedelta(days=60))
        after = Operator.objects.create(
            employee_id="P2", full_name="Se cargo despues", cost_center=site
        )
        _born(after, timezone.now() - timedelta(days=10))

        assert _cards(cutoff)["credentials"]["total"] == 1
        assert _cards(timezone.localdate())["credentials"]["total"] == 2

    @pytest.mark.django_db
    def test_the_same_holds_for_the_fleet(self, site):
        """La flota se cuenta igual: el informe dice cuántas aeronaves había."""
        cutoff = timezone.localdate() - timedelta(days=40)
        old = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M3E",
            manufacturer="DJI",
            cost_center=site,
        )
        _born(old, timezone.now() - timedelta(days=60))
        new = Aircraft.objects.create(
            registration="RPA-2",
            type="RPA",
            model="M3E",
            manufacturer="DJI",
            cost_center=site,
        )
        _born(new, timezone.now() - timedelta(days=10))

        assert _cards(cutoff)["fleet"]["total"] == 1
        assert _cards(timezone.localdate())["fleet"]["total"] == 2

    @pytest.mark.django_db
    def test_a_row_created_today_still_counts_today(self, site):
        """**El panel no puede cambiar, y ésta es la comprobación.**

        El corte va sin parámetro y siempre; su seguridad depende por completo
        de que `created_at <= hoy` sea verdadero para todo lo que existe. Si una
        fila recién creada se cayera del conteo, el panel habría empezado a
        mentir en silencio el día que esto se escribió.
        """
        Operator.objects.create(employee_id="P9", full_name="Recien", cost_center=site)

        assert _cards(timezone.localdate())["credentials"]["total"] == 1

    @pytest.mark.django_db
    def test_the_payload_carries_the_cut_roster(self, site):
        """Y que llegue al informe, no sólo a la función."""
        old = Operator.objects.create(
            employee_id="P1", full_name="Ya estaba", cost_center=site
        )
        _born(old, timezone.make_aware(timezone.datetime(2026, 7, 15, 12, 0)))
        new = Operator.objects.create(
            employee_id="P2", full_name="Septiembre", cost_center=site
        )
        _born(new, timezone.make_aware(timezone.datetime(2026, 9, 10, 12, 0)))

        payload, _missing = build(date(2026, 8, 1))

        assert payload["meta"]["cutoff"] == "2026-08-31"
        assert payload["kpis"]["operators_total"]["value"] == 1


class TestMissingIsNotLapsed:
    @pytest.mark.django_db
    def test_the_report_splits_the_gap_the_way_it_gets_fixed(self, site):
        """Los 8 del informe emitido eran 7 + 1, y cada mitad es otro trabajo.

        Una fecha ausente es un dato que nadie cargó — y por eso ni siquiera
        genera alerta (`LV-29`) ni aparece en la lista de vencimientos. Una
        vencida es un trámite ante la DGAC. Sumadas, la cifra no dice a quién
        llamar.
        """
        _existed_in_july(
            Operator.objects.create(
                employee_id="P1", full_name="Sin fecha", cost_center=site
            ),
            Operator.objects.create(
                employee_id="P2",
                full_name="Vencida",
                cost_center=site,
                credential_expiry=CUTOFF - timedelta(days=5),
            ),
            Operator.objects.create(
                employee_id="P3",
                full_name="Vigente",
                cost_center=site,
                credential_expiry=CUTOFF + timedelta(days=90),
            ),
        )

        payload, _missing = build(PERIOD)
        kpis = payload["kpis"]

        assert kpis["operators_total"]["value"] == 3
        assert kpis["operators_credentialed"]["value"] == 1
        # Los dos que faltan, separados: uno se carga, el otro se renueva.
        assert kpis["credentials_missing"]["value"] == 1
        assert kpis["credentials_lapsed"]["value"] == 1

    @pytest.mark.django_db
    def test_the_insurance_gap_splits_the_same_way(self, site):
        _existed_in_july(
            Aircraft.objects.create(
                registration="RPA-1",
                type="RPA",
                model="M3E",
                manufacturer="DJI",
                cost_center=site,
            ),
            Aircraft.objects.create(
                registration="RPA-2",
                type="RPA",
                model="M3E",
                manufacturer="DJI",
                cost_center=site,
                insurance_expiry=CUTOFF - timedelta(days=3),
            ),
        )

        payload, _missing = build(PERIOD)
        kpis = payload["kpis"]

        assert kpis["insurance_missing"]["value"] == 1
        assert kpis["insurance_lapsed"]["value"] == 1

    @pytest.mark.django_db
    def test_both_halves_are_zero_and_not_missing_when_everything_is_in_order(
        self, site
    ):
        """Cero **es** un dato acá: se miró y no falta ninguno.

        Si estas hojas salieran como `None`, el informe diría "pendiente" sobre
        una brecha que sí se midió y que vale cero — el error simétrico al que
        toda esta app viene evitando.
        """
        _existed_in_july(
            Operator.objects.create(
                employee_id="P1",
                full_name="Al dia",
                cost_center=site,
                credential_expiry=date(2027, 1, 1),
            )
        )

        payload, missing = build(PERIOD)

        # El operador se cuenta: si no, los dos ceros de abajo serían ciertos
        # sobre un padrón vacío y el test pasaría sin medir nada.
        assert payload["kpis"]["operators_total"]["value"] == 1
        assert payload["kpis"]["credentials_missing"]["value"] == 0
        assert payload["kpis"]["credentials_lapsed"]["value"] == 0
        assert "kpis.credentials_missing" not in missing


class TestWhatTheCutoffCannotDo:
    @pytest.mark.django_db
    def test_an_archived_row_is_gone_from_every_period(self, site):
        """**El límite, fijado a propósito para que nadie lo lea de más.**

        Archivar una ficha la saca también de los informes anteriores, porque no
        hay historial de `is_active` que consultar. El corte deja de contar lo
        que no existía; no reconstruye lo que había. Un informe **congelado** no
        sufre esto —dibuja su payload guardado—, y por eso congelar (`R5`) no es
        un lujo: es lo que vuelve estable una cifra que acá no puede serlo.
        """
        operator = Operator.objects.create(
            employee_id="P1", full_name="Se archivo", cost_center=site
        )
        _born(operator, timezone.make_aware(timezone.datetime(2026, 7, 1, 12, 0)))

        payload, _missing = build(date(2026, 8, 1))
        assert payload["kpis"]["operators_total"]["value"] == 1

        operator.is_active = False
        operator.save()

        payload, _missing = build(date(2026, 8, 1))
        assert payload["kpis"]["operators_total"]["value"] == 0
