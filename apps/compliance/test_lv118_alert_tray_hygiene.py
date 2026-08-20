"""LV-118: higiene de la bandeja de alertas.

Pedido del usuario el 2026-08-20 con captura de producción: ocho filas, de las
que sólo cuatro eran trabajo — las otras cuatro eran el residuo duplicado
anterior a `LV-111`, ya resuelto, compitiendo por la atención con lo pendiente.
Textual: *"cómo organizarlas, distribuirlas y darle el seguimiento, sobre todo
con los errores o repetidas para que no existan en el flujo"*.

Cuatro cosas, ninguna con migración ni campo nuevo:

1. La bandeja **abre en "Sin resolver"**. Lo resuelto sigue a un clic.
2. El vencimiento que muestra una alerta es **el que la disparó**, no el que el
   registro tiene hoy. Es una corrección, no una mejora: la captura enseña dos
   alertas de `RPA-5532` levantadas por una póliza vencida el 2026-08-08 que
   decían "vencimiento 2027-08-04", la fecha que dejó la renovación después.
3. La **severidad se deriva** del vencimiento y ordena la bandeja.
4. `generate_alerts` **delata** las repetidas que ya están escritas.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="OPS", name="Operations")


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Seguros JAC por vencer",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


@pytest.fixture
def aircraft(cost_center):
    return Aircraft.objects.create(
        registration="RPA-5532",
        serial_number="SN-5532",
        cost_center=cost_center,
        insurance_expiry=TODAY - timedelta(days=12),
    )


def _client():
    user = User.objects.create_user("ops", "ops@test.com", "password")
    user.user_permissions.add(
        Permission.objects.get(codename="view_alert"),
        Permission.objects.get(codename="change_alert"),
    )
    client = Client()
    assert client.login(username="ops", password="password")
    return client


def _alert(rule, record, *, watched_value, resolved=False):
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(type(record)),
        object_id=record.pk,
        message="Vigencia por vencer",
        watched_value=watched_value,
    )
    if resolved:
        alert.resolve(reason="Se actualiza el seguro")
    return alert


class TestTheTrayOpensOnWhatIsPending:
    @pytest.mark.django_db
    def test_a_resolved_alert_is_not_in_the_default_view(self, rule, aircraft):
        open_alert = _alert(rule, aircraft, watched_value="2026-08-08")
        resolved = _alert(rule, aircraft, watched_value="2027-08-04", resolved=True)

        content = _client().get(reverse("alert-list")).content.decode()

        assert reverse("alert-resolve", args=[open_alert.pk]) in content
        assert reverse("alert-reopen", args=[resolved.pk]) not in content

    @pytest.mark.django_db
    def test_asking_for_all_still_shows_everything(self, rule, aircraft):
        """Lo resuelto es evidencia ISO 10.2: se saca del flujo, no del sistema."""
        resolved = _alert(rule, aircraft, watched_value="2027-08-04", resolved=True)

        content = (
            _client()
            .get(reverse("alert-list"), {"is_resolved": "all"})
            .content.decode()
        )

        assert reverse("alert-reopen", args=[resolved.pk]) in content

    @pytest.mark.django_db
    def test_the_picker_shows_the_filter_that_is_actually_applied(self, rule, aircraft):
        """Un listado que recorta sin decirlo es peor que uno largo.

        Llegar sin parámetros ya no significa "todas", así que el selector tiene
        que venir con "Sin resolver" marcado y no con "Todas las alertas".
        """
        _alert(rule, aircraft, watched_value="2026-08-08")

        content = _client().get(reverse("alert-list")).content.decode()

        assert '<option value="false" selected>' in content
        assert '<option value="all" selected>' not in content


class TestTheExpiryIsTheOneThatTriggeredIt:
    @pytest.mark.django_db
    def test_a_resolved_alert_keeps_the_date_that_raised_it(self, rule, aircraft):
        """El caso exacto de la captura del 2026-08-20.

        La alerta se levantó por el 2026-08-08 y después alguien renovó la
        póliza hasta el 2027-08-04. La fila tiene que seguir diciendo por qué se
        levantó, no lo que pasó luego.
        """
        alert = _alert(rule, aircraft, watched_value="2026-08-08", resolved=True)
        aircraft.insurance_expiry = TODAY + timedelta(days=349)
        aircraft.save(update_fields=["insurance_expiry"])

        alert.refresh_from_db()
        assert alert.triggering_date.isoformat() == "2026-08-08"
        assert alert.urgency == "overdue"

        content = (
            _client()
            .get(reverse("alert-list"), {"is_resolved": "all"})
            .content.decode()
        )
        assert "2026-08-08" in content
        assert aircraft.insurance_expiry.isoformat() not in content

    @pytest.mark.django_db
    def test_a_rule_watching_a_status_has_no_expiry_to_show(self, aircraft):
        """`retired` no parsea como fecha, y eso no es un error: es una alerta
        que no habla de una vigencia. Devuelve `None`, no revienta."""
        status_rule = AlertRule.objects.create(
            name="Aeronaves dadas de baja",
            entity_type="registry.aircraft",
            field_to_watch="status",
        )
        alert = _alert(status_rule, aircraft, watched_value="retired")

        assert alert.triggering_date is None
        assert alert.urgency is None

    @pytest.mark.django_db
    def test_an_alert_created_without_a_value_shows_no_date(self, rule, aircraft):
        """Vacío significa "el campo no tenía valor al crearla". Leer el
        registro en vivo para rellenarlo sería reinventar el defecto."""
        alert = _alert(rule, aircraft, watched_value="")

        assert alert.triggering_date is None


class TestSeverityIsDerivedNotEdited:
    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "days_out, expected",
        [
            (-90, "overdue"),
            (-1, "overdue"),
            (3, "due_7"),
            (12, "due_15"),
            (25, "due_30"),
            (349, "later"),
        ],
    )
    def test_the_tier_matches_the_daily_digest(
        self, rule, aircraft, days_out, expected
    ):
        """Los mismos cortes que `bucket_for`: dos pantallas contando lo mismo
        con tramos distintos serían dos versiones de la verdad."""
        value = (TODAY + timedelta(days=days_out)).isoformat()
        alert = _alert(rule, aircraft, watched_value=value)

        assert alert.urgency == expected
        assert alert.urgency_css == Alert.URGENCY_CSS[expected]

    @pytest.mark.django_db
    def test_the_tray_puts_the_worst_first(self, rule, cost_center):
        """`LV-112` no podía ordenar por vencimiento sin resolver la
        GenericForeignKey de cada fila (el N+1 de `LV-106`). Con el valor en una
        columna desde `LV-111`, la base ordena sola — y en ISO el orden
        lexicográfico **es** el cronológico."""
        order = ["2026-05-20", "2026-08-08", "2026-09-05"]
        for index, value in enumerate(reversed(order)):
            record = Aircraft.objects.create(
                registration=f"RPA-{4000 + index}",
                serial_number=f"SN-{4000 + index}",
                cost_center=cost_center,
                insurance_expiry=TODAY + timedelta(days=index),
            )
            _alert(rule, record, watched_value=value)

        response = _client().get(reverse("alert-list"))
        content = response.content.decode()

        assert [alert.watched_value for alert in response.context["objects"]] == order
        # Y el color acompaña al orden: lo vencido grita, lo de septiembre no.
        assert "bg-danger" in content

    @pytest.mark.django_db
    def test_an_alert_without_a_value_does_not_head_the_tray(
        self, rule, aircraft, cost_center
    ):
        """ "" es lo primero que ordena en texto, así que sin la anotación una
        alerta sin fecha encabezaría la bandeja por delante de una póliza
        vencida hace tres meses."""
        overdue = _alert(rule, aircraft, watched_value="2026-05-20")
        other = Aircraft.objects.create(
            registration="RPA-9001",
            serial_number="SN-9001",
            cost_center=cost_center,
        )
        valueless = _alert(rule, other, watched_value="")

        objects = list(_client().get(reverse("alert-list")).context["objects"])

        assert objects == [overdue, valueless]


class TestRepeatedAlertsAreDenounced:
    @pytest.mark.django_db
    def test_the_daily_job_names_a_repeated_pair(self, rule, aircraft, capsys):
        """`LV-111` cerró la causa pero no dice nada de lo ya escrito. En
        producción quedaron cuatro filas y la única forma de enterarse fue que
        el usuario las viera en pantalla tres días después del despliegue."""
        _alert(rule, aircraft, watched_value="2026-08-08", resolved=True)
        _alert(rule, aircraft, watched_value="2026-08-08", resolved=True)

        call_command("generate_alerts")

        output = capsys.readouterr().out
        assert "Repeated alerts (LV-118)" in output
        assert "Seguros JAC por vencer" in output
        assert "2026-08-08" in output

    @pytest.mark.django_db
    def test_it_stays_quiet_when_there_is_nothing_to_say(self, rule, aircraft, capsys):
        """Un aviso que sale todos los días enseña a no leerlo."""
        _alert(rule, aircraft, watched_value="2026-08-08", resolved=True)

        call_command("generate_alerts")

        assert "Repeated alerts" not in capsys.readouterr().out

    @pytest.mark.django_db
    def test_two_alerts_for_different_values_are_not_repeated(
        self, rule, aircraft, capsys
    ):
        """La renovación legítima: mismo registro, misma regla, valor nuevo. Es
        exactamente el caso que `LV-111` decidió **no** suprimir, así que
        delatarlo acá contradiría al motor."""
        _alert(rule, aircraft, watched_value="2026-08-08", resolved=True)
        _alert(rule, aircraft, watched_value="2027-08-04")

        call_command("generate_alerts")

        assert "Repeated alerts" not in capsys.readouterr().out

    @pytest.mark.django_db
    def test_it_counts_on_the_same_key_the_engine_dedupes_on(
        self, rule, operator_record, aircraft, capsys
    ):
        """Dos registros distintos con el mismo valor no son una repetición."""
        _alert(rule, aircraft, watched_value="2026-08-08")
        _alert(rule, operator_record, watched_value="2026-08-08")

        call_command("generate_alerts")

        assert "Repeated alerts" not in capsys.readouterr().out


@pytest.fixture
def operator_record(cost_center):
    return Operator.objects.create(
        employee_id="P1",
        full_name="Carlos Peñailillo Latorre",
        cost_center=cost_center,
    )
