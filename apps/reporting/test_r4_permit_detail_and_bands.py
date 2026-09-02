"""R4: la tabla permiso a permiso, el próximo vencimiento y los semáforos.

Lo que estos tests protegen:

1. **Que un trámite no se lea como una habilitación.** Un permiso solicitado no
   tiene vigencia (`LV-219`) y no autoriza a volar; mezclarlo con los vigentes
   en la misma tabla lo sugiere, y sus días tienen que ser un guion y nunca un
   cero — cero afirmaría que vence hoy.
2. **Que el semáforo del permiso use el vocabulario de `UX-01` y su propio
   corte.** El riesgo anotado en el plan era estrenar una tercera escala de
   color; lo que cambia es el umbral (30/60 en vez de 7/15/30), no los nombres.
3. **Que la concentración conteste al riesgo real**, que es si la faena puede
   volar sin esa persona.
4. **Que la tabla no cueste una consulta por fila.**
"""

from datetime import date, timedelta

import pytest

from apps.compliance.kpis import (
    PERMIT_BAND_CRITICAL,
    PERMIT_BAND_NOMINAL,
    PERMIT_BAND_WARNING,
    permit_band,
    permit_counts,
)
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.builder import build, collect_concentration, collect_permits

PERIOD = date(2026, 8, 1)
CUTOFF = date(2026, 8, 31)


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def other_site(db):
    return CostCenter.objects.create(
        code="CC691", name="El Mauro", operates_flights=True
    )


def _permit(site, folio_number, *, days=None, status=None, **kwargs):
    """Un permiso cuyo vencimiento cae a `days` del corte."""
    permit = FlightPermission.objects.create(
        cost_center=site,
        purpose="photogrammetry",
        status=status or FlightPermission.STATUS_APPROVED,
        permission_number=kwargs.pop("dgac", f"60{folio_number:02d}"),
        location="Site",
        area_type="unpopulated",
        valid_from=CUTOFF - timedelta(days=30) if days is not None else None,
        valid_until=CUTOFF + timedelta(days=days) if days is not None else None,
        **kwargs,
    )
    return permit


class TestTheBandKeepsTheVocabularyAndChangesTheThreshold:
    @pytest.mark.parametrize(
        ("days", "band"),
        [
            (-5, PERMIT_BAND_CRITICAL),
            (0, PERMIT_BAND_CRITICAL),
            (30, PERMIT_BAND_CRITICAL),
            (31, PERMIT_BAND_WARNING),
            (60, PERMIT_BAND_WARNING),
            (61, PERMIT_BAND_NOMINAL),
        ],
    )
    def test_the_thresholds_are_the_ones_the_issued_report_draws(self, days, band):
        """La leyenda del informe emitido: crítico ≤30, por vencer 31–60,
        vigente >60."""
        assert permit_band(days) == band

    def test_without_a_validity_there_is_no_band(self):
        """**Un trámite no es un vencimiento.**

        Un permiso solicitado no tiene vigencia porque la DGAC no ha resuelto
        (`LV-219`). Pintarlo de rojo sería declarar incumplimiento sobre una
        espera que no es de nadie.
        """
        assert permit_band(None) is None

    def test_the_names_are_the_ones_ux01_fixed(self):
        """El riesgo que el plan anotó era estrenar una **tercera** escala de
        color. Los cortes cambian; los nombres no."""
        from apps.compliance.digest import BUCKET_BADGE_CSS

        app_levels = {css.removeprefix("sev-") for css in BUCKET_BADGE_CSS.values()}

        assert {
            PERMIT_BAND_CRITICAL,
            PERMIT_BAND_WARNING,
            PERMIT_BAND_NOMINAL,
        } <= app_levels


class TestTheSixtyDayWindow:
    @pytest.mark.django_db
    def test_it_counts_what_the_issued_report_counts(self, site):
        """El informe emitido dice "4 por vencer en 60 días, uno en 17"."""
        _permit(site, 1, days=17)
        _permit(site, 2, days=45)
        _permit(site, 3, days=90)

        counts = permit_counts(CUTOFF)

        assert counts["soon"] == 1  # la ventana del panel, 30 días
        assert counts["soon_60"] == 2

    @pytest.mark.django_db
    def test_the_panel_window_is_left_alone(self, site):
        """`soon` no se reemplazó por 60: el panel pregunta "qué se me viene
        este mes" y el informe "qué hay que empezar a tramitar"."""
        _permit(site, 1, days=45)

        assert permit_counts(CUTOFF)["soon"] == 0


class TestTheDetailTable:
    @pytest.mark.django_db
    def test_a_permit_carries_its_folio_operators_and_aircraft(self, site):
        permit = _permit(site, 1, days=88, dgac="6405")
        permit.operators.add(
            Operator.objects.create(
                employee_id="P1", full_name="Fernando Jopia Tapia", cost_center=site
            )
        )
        permit.aircraft_fleet.add(
            Aircraft.objects.create(
                registration="RPA-4883",
                type="RPA",
                model="M3E",
                manufacturer="DJI",
                cost_center=site,
            )
        )

        (row,) = collect_permits(CUTOFF)

        assert row["folio"] == permit.internal_folio
        assert row["dgac_number"] == "6405"
        assert row["cost_centre"] == "CC738"
        assert row["operators"] == ["Fernando Jopia Tapia"]
        assert row["aircraft"] == ["RPA-4883"]
        assert row["days_remaining"] == 88
        assert row["band"] == PERMIT_BAND_NOMINAL
        assert row["in_force"]

    @pytest.mark.django_db
    def test_a_requested_permit_is_listed_but_not_in_force(self, site):
        """**El que más importa de esta clase.**

        Una solicitud en trámite no habilita a volar. Aparece —el informe la
        lista en su propio bloque— pero con `in_force` en falso, sin días y sin
        banda: un cero ahí se leería como "vence hoy".
        """
        _permit(site, 1, status=FlightPermission.STATUS_REQUESTED, dgac="")

        (row,) = collect_permits(CUTOFF)

        assert not row["in_force"]
        assert row["days_remaining"] is None
        assert row["band"] is None
        assert row["dgac_number"] is None

    @pytest.mark.django_db
    def test_a_lapsed_permit_is_in_the_table_but_not_in_force(self, site):
        """Vencido y sin cerrar: sigue vivo como fila y ya no habilita.

        Es la señal de que el trabajo nocturno de `LV-83` no corrió, así que
        esconderlo sería esconder el diagnóstico.
        """
        _permit(site, 1, days=-10)

        (row,) = collect_permits(CUTOFF)

        assert not row["in_force"]
        assert row["days_remaining"] == -10
        assert row["band"] == PERMIT_BAND_CRITICAL

    @pytest.mark.django_db
    def test_the_earliest_expiry_comes_first(self, site):
        """El orden del informe emitido: el que obliga a actuar, arriba."""
        _permit(site, 1, days=88)
        _permit(site, 2, days=17)

        assert [row["days_remaining"] for row in collect_permits(CUTOFF)] == [17, 88]

    @pytest.mark.django_db
    def test_the_table_does_not_cost_a_query_per_row(
        self, site, django_assert_max_num_queries
    ):
        """Cada permiso nombra sus operadores y sus aeronaves: sin los dos
        `prefetch_related` son 2N consultas, y el payload se construye también
        desde un trabajo nocturno donde nadie mira el reloj."""
        for index in range(6):
            permit = _permit(site, index, days=40 + index)
            permit.operators.add(
                Operator.objects.create(
                    employee_id=f"P{index}",
                    full_name=f"Piloto {index}",
                    cost_center=site,
                )
            )

        with django_assert_max_num_queries(4):
            collect_permits(CUTOFF)


class TestTheNextExpiryPerCostCentre:
    @pytest.mark.django_db
    def test_it_is_the_first_to_fall_and_not_the_last(self, site):
        """`Min` y no `Max`: con siete permisos vigentes el que manda es el
        primero en caer. `Max` habría mostrado la fecha más cómoda y escondido
        justamente la urgente."""
        _permit(site, 1, days=88)
        _permit(site, 2, days=17)

        payload, _missing = build(PERIOD)
        (row,) = payload["cost_centres"]

        assert row["days_remaining"] == 17
        assert row["next_expiry"] == (CUTOFF + timedelta(days=17)).isoformat()
        assert row["band"] == PERMIT_BAND_CRITICAL

    @pytest.mark.django_db
    def test_a_site_without_permits_has_no_date_and_the_worst_band(self, site):
        """§4.2 del SPEC: el semáforo de la faena es **el peor** de sus
        habilitantes, nunca el promedio. No poder volar es lo peor de la escala,
        no la ausencia de una."""
        payload, _missing = build(PERIOD)
        (row,) = payload["cost_centres"]

        assert row["next_expiry"] is None
        assert row["days_remaining"] is None
        assert row["band"] == PERMIT_BAND_CRITICAL

    @pytest.mark.django_db
    def test_a_requested_permit_does_not_become_a_next_expiry(self, site):
        """Una solicitud no da fecha de vencimiento a la faena."""
        _permit(site, 1, status=FlightPermission.STATUS_REQUESTED)

        payload, _missing = build(PERIOD)
        (row,) = payload["cost_centres"]

        assert row["next_expiry"] is None
        assert row["permits_awaiting"] == 1


class TestConcentration:
    def test_a_site_with_a_substitute_does_not_depend_on_one_person(self):
        """**La definición que responde al riesgo real.**

        Si alguno de los permisos de la faena designa a otra persona, la faena
        sigue pudiendo volar sin la primera. Contar "faenas con algún permiso de
        un solo operador" habría inflado la cifra con faenas que sí tienen
        suplente — y ese número habría ido a la DGAC.
        """
        permits = [
            {"in_force": True, "cost_centre": "CC738", "operators": ["Ana"]},
            {"in_force": True, "cost_centre": "CC738", "operators": ["Beto"]},
        ]

        result = collect_concentration(permits)

        assert result["permits_with_one_operator"] == 2
        assert result["cost_centres_on_one_person"] == []

    def test_a_site_whose_every_permit_names_the_same_person_does(self):
        permits = [
            {"in_force": True, "cost_centre": "CC738", "operators": ["Ana"]},
            {"in_force": True, "cost_centre": "CC738", "operators": ["Ana"]},
            {"in_force": True, "cost_centre": "CC691", "operators": ["Ana", "Beto"]},
        ]

        result = collect_concentration(permits)

        assert result["cost_centres_on_one_person"] == ["CC738"]

    def test_a_requested_permit_does_not_count_as_cover(self):
        """Una solicitud en trámite no habilita a nadie, así que el suplente que
        sólo aparece ahí no es suplente todavía."""
        permits = [
            {"in_force": True, "cost_centre": "CC738", "operators": ["Ana"]},
            {"in_force": False, "cost_centre": "CC738", "operators": ["Beto"]},
        ]

        result = collect_concentration(permits)

        assert result["cost_centres_on_one_person"] == ["CC738"]
        assert result["permits_in_force"] == 1


class TestItAllReachesThePage:
    @pytest.mark.django_db
    def test_the_permit_row_and_the_bands_are_rendered(self, client, site):
        from django.contrib.auth.models import Permission, User

        user = User.objects.create_user("reader", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        permit = _permit(site, 1, days=17, dgac="5808")
        permit.operators.add(
            Operator.objects.create(
                employee_id="P1", full_name="Alex Lizama Paz", cost_center=site
            )
        )
        client.force_login(user)

        body = client.get("/reporting/monthly/", {"period": "2026-08"}).content.decode()

        assert permit.internal_folio in body
        assert "5808" in body
        assert "Alex Lizama Paz" in body
        assert "rpt-sev-critical" in body
        # Y el vocabulario viejo no vuelve por la puerta de atrás.
        assert "rpt-est-none" not in body

    @pytest.mark.django_db
    def test_the_dates_read_day_first_and_never_iso(self, client, site):
        """**Encontrado mirando la pantalla, no corriendo tests.**

        El payload guarda ISO porque es JSON, y recortar esa cadena a sus cinco
        últimos caracteres daba `08-01` para el 1 de agosto — que en un
        documento chileno se lee como el 8 de enero. Una fecha que se puede leer
        al revés no es un detalle de formato en un papel que va a la DGAC.
        """
        from django.contrib.auth.models import Permission, User

        user = User.objects.create_user("lector", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        _permit(site, 1, days=17)  # vence el 17-09-2026, empieza el 01-08-2026
        client.force_login(user)

        body = client.get("/reporting/monthly/", {"period": "2026-08"}).content.decode()

        assert "01-08 → " in body
        assert "17-09-2026" in body
        assert "2026-09-17" not in body
