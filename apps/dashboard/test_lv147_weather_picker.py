"""LV-147: la ubicación del pronóstico se elige, y el título deja de mentir.

Textual del usuario: *"el panel ahora me muestra el clima de este sector; ¿es
recomendado? porque sale tan directo […] donde yo pueda elegir la ubicación del
permiso e ir actualizando, algo más dinámico, ya que pierde sentido tener el
último solamente"*.

El proveedor nunca se llama de verdad: `forecast_for` se reemplaza por un
grabador, así que lo que se afirma es **cuántas veces** y **para qué (lugar,
día)** pregunta el panel. Con selector eso importa más que antes: una elección no
puede convertirse en una petición por opción ofrecida.

Y la elección **nunca abre una puerta**: se resuelve dentro de la lista de
candidatos, que ya está acotada por permiso, estado y filtro de faena. Los tests
de "cae al automático" son los que fijan esa propiedad, uno por cada forma de
llegar con un valor que no corresponde.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()

FORECAST = {
    "temperature_2m_max": 17.4,
    "temperature_2m_min": 3.9,
    "wind_speed_10m_max": 8.1,
    "wind_gusts_10m_max": 12.7,
    "precipitation_sum": 0.0,
    "precipitation_probability_max": 5,
    "condition": "cloudy",
    "units": {"wind_speed_10m_max": "m/s", "temperature_2m_max": "°C"},
    "date": TODAY.isoformat(),
}


@pytest.fixture
def asked(monkeypatch):
    calls = []

    def forecast_for(latitude, longitude, target_date):
        calls.append((float(latitude), float(longitude), target_date))
        return FORECAST

    monkeypatch.setattr("apps.core.weather.forecast_for", forecast_for)
    return calls


@pytest.fixture
def client_with_everything(db):
    user = User.objects.create_user("panel", "p@x.cl")
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=["view_flightpermission", "view_costcenter", "view_aircraft"]
        )
    )
    client = Client()
    client.force_login(user)
    return client


def _cc(code="CC1", **kwargs):
    return CostCenter.objects.create(code=code, name=code, **kwargs)


def _permission(cost_center, *, valid_from=None, **kwargs):
    valid_from = valid_from or TODAY
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        area_type="unpopulated",
        valid_from=valid_from,
        valid_until=kwargs.pop("valid_until", valid_from + timedelta(days=30)),
        location=kwargs.pop("location", "Site"),
        status=kwargs.pop("status", "approved"),
        latitude=kwargs.pop("latitude", -31.9),
        longitude=kwargs.pop("longitude", -70.7),
        **kwargs,
    )


def _fleet(cost_center=None):
    """Una aeronave cualquiera, para que el panel no dibuje el estado inicial.

    Con el padrón vacío la pantalla muestra la guía de "empieza tu operación" en
    vez del panel, así que los tests que afirman **HTML** necesitan un registro;
    los que afirman contexto, no.
    """
    return Aircraft.objects.create(
        registration="RPA-4025",
        type="Multirotor",
        model="M4E",
        manufacturer="DJI",
        cost_center=cost_center,
    )


def _panel(client, **params):
    return client.get(reverse("dashboard"), params)


@pytest.mark.django_db
class TestTheChoiceList:
    def test_permits_and_sites_are_both_offered(self, asked, client_with_everything):
        cost_center = _cc("CC738", latitude=-31.8, longitude=-70.6)
        _permission(cost_center)

        context = _panel(client_with_everything).context

        assert len(context["weather_permit_choices"]) == 1
        assert len(context["weather_site_choices"]) == 1

    def test_the_list_respects_the_cost_center_filter(
        self, asked, client_with_everything
    ):
        mine = _cc("CC738", latitude=-31.8, longitude=-70.6)
        other = _cc("CC861", latitude=-22.3, longitude=-68.9)
        _permission(mine)
        _permission(other)

        context = _panel(client_with_everything, cost_center=mine.pk).context

        assert len(context["weather_permit_choices"]) == 1
        assert len(context["weather_site_choices"]) == 1

    def test_a_permit_without_coordinates_is_not_offered(
        self, asked, client_with_everything
    ):
        cost_center = _cc("CC738")
        _permission(cost_center, latitude=None, longitude=None)

        assert _panel(client_with_everything).context["weather_permit_choices"] == []

    def test_a_site_without_coordinates_is_not_offered(
        self, asked, client_with_everything
    ):
        _cc("CC738")

        assert _panel(client_with_everything).context["weather_site_choices"] == []

    def test_without_view_flightpermission_no_permit_is_offered(self, asked, db):
        cost_center = _cc("CC738", latitude=-31.8, longitude=-70.6)
        _permission(cost_center)
        user = User.objects.create_user("limited", "l@x.cl")
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_costcenter"])
        )
        client = Client()
        client.force_login(user)

        context = _panel(client).context

        assert context["weather_permit_choices"] == []
        assert len(context["weather_site_choices"]) == 1


@pytest.mark.django_db
class TestResolvingTheChoice:
    def test_a_chosen_permit_wins_over_the_next_one(
        self, asked, client_with_everything
    ):
        cost_center = _cc("CC738")
        soonest = _permission(cost_center, latitude=-31.9, longitude=-70.7)
        later = _permission(
            cost_center,
            valid_from=TODAY + timedelta(days=10),
            latitude=-22.3,
            longitude=-68.9,
        )

        context = _panel(
            client_with_everything, weather=f"permission:{later.pk}"
        ).context

        assert context["weather_folio"] == later.internal_folio
        assert context["weather_folio"] != soonest.internal_folio
        assert asked == [(-22.3, -68.9, TODAY + timedelta(days=10))]

    def test_a_chosen_site_is_used(self, asked, client_with_everything):
        cost_center = _cc("CC738", latitude=-33.4, longitude=-70.6)
        _permission(cost_center)

        context = _panel(
            client_with_everything, weather=f"cost_center:{cost_center.pk}"
        ).context

        assert context["weather_source"] == "cost_center"
        assert asked == [(-33.4, -70.6, TODAY)]

    @pytest.mark.parametrize(
        "value",
        [
            "permission",
            ":",
            "x:y",
            "permission:no-es-uuid",
            "permission:00000000-0000-0000-0000-000000000000",
            "cost_center:00000000-0000-0000-0000-000000000000",
        ],
    )
    def test_a_value_that_does_not_resolve_falls_back_to_automatic(
        self, asked, client_with_everything, value
    ):
        cost_center = _cc("CC738")
        permit = _permission(cost_center)

        context = _panel(client_with_everything, weather=value).context

        assert context["weather_folio"] == permit.internal_folio
        assert context["weather_scope"] == "next"
        assert len(asked) == 1

    def test_a_permit_of_another_cost_center_falls_back_when_filtering(
        self, asked, client_with_everything
    ):
        mine = _cc("CC738")
        other = _cc("CC861")
        mine_permit = _permission(mine, latitude=-31.9, longitude=-70.7)
        other_permit = _permission(other, latitude=-22.3, longitude=-68.9)

        context = _panel(
            client_with_everything,
            cost_center=mine.pk,
            weather=f"permission:{other_permit.pk}",
        ).context

        assert context["weather_folio"] == mine_permit.internal_folio
        assert asked == [(-31.9, -70.7, TODAY)]

    def test_a_permit_the_user_may_not_see_leaks_nothing(self, asked, db):
        cost_center = _cc("CC738", latitude=-33.4, longitude=-70.6)
        hidden = _permission(
            cost_center, latitude=-22.3, longitude=-68.9, area_name="Talabre"
        )
        user = User.objects.create_user("limited", "l@x.cl")
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_costcenter"])
        )
        client = Client()
        client.force_login(user)

        response = _panel(client, weather=f"permission:{hidden.pk}")

        assert hidden.internal_folio not in response.content.decode()
        assert "Talabre" not in response.content.decode()
        assert (-22.3, -68.9, TODAY) not in asked


@pytest.mark.django_db
class TestCost:
    def test_one_call_per_render_even_with_a_choice_made(
        self, asked, client_with_everything
    ):
        cost_center = _cc("CC738", latitude=-33.4, longitude=-70.6)
        permits = [
            _permission(cost_center, valid_from=TODAY + timedelta(days=index))
            for index in range(12)
        ]

        _panel(client_with_everything, weather=f"permission:{permits[7].pk}")

        assert len(asked) == 1


@pytest.mark.django_db
class TestTheTitleDoesNotLie:
    def test_it_says_next_flight_only_when_automatic(
        self, asked, client_with_everything
    ):
        _permission(_cc("CC738"))

        assert _panel(client_with_everything).context["weather_scope"] == "next"

    def test_a_chosen_permission_gets_its_own_heading(
        self, asked, client_with_everything
    ):
        cost_center = _cc("CC738")
        permit = _permission(cost_center)

        context = _panel(
            client_with_everything, weather=f"permission:{permit.pk}"
        ).context

        assert context["weather_scope"] == "permission"

    def test_the_site_fallback_no_longer_claims_a_next_flight(
        self, asked, client_with_everything
    ):
        # Defecto vigente antes de LV-147: sin ningún permiso con coordenadas la
        # tarjeta caía al sitio de la faena y se seguía titulando "donde vuelas
        # ahora", sin que hubiera vuelo ninguno.
        cost_center = _cc("CC738", latitude=-33.4, longitude=-70.6)

        context = _panel(client_with_everything, cost_center=cost_center.pk).context

        assert context["weather_scope"] == "site"


@pytest.mark.django_db
class TestOnThePage:
    def test_lv216_the_resolution_still_happens_without_the_card(
        self, asked, client_with_everything
    ):
        """**LV-216 retiró la tarjeta del panel** —*"no es necesario que muestre el
        clima […] además está fallando"*— así que estos tests pasan de afirmar el
        HTML del selector a afirmar que **la resolución sigue ocurriendo**.

        Se llamaban `test_the_resolved_choice_is_the_selected_option` y
        `test_the_cost_center_filter_travels_in_a_hidden_input`, y comprobaban dos
        cosas del formulario del selector: cuál opción salía marcada y que el
        filtro de faena viajaba en un input oculto. Los dos elementos vivían dentro
        del bloque retirado.

        Lo que sigue vivo es lo que importa para reponer la tarjeta: `LV-147`
        resuelve la ubicación a partir del parámetro y deja el resultado en el
        contexto. 37 de sus tests no se tocaron.
        """
        _fleet()
        cost_center = _cc("CC738")
        permit = _permission(cost_center)

        response = _panel(client_with_everything, weather=f"permission:{permit.pk}")

        assert response.context["weather_selection"] == f"permission:{permit.pk}"
        # Y el selector ya no se dibuja: es el retiro.
        assert 'name="weather"' not in response.content.decode().split("</form>")[1]

    def test_the_filter_form_carries_the_weather_choice_back(
        self, asked, client_with_everything
    ):
        _fleet()
        cost_center = _cc("CC738")
        permit = _permission(cost_center)

        content = _panel(
            client_with_everything, weather=f"permission:{permit.pk}"
        ).content.decode()

        assert f'name="weather" value="permission:{permit.pk}"' in content

    def test_lv216_the_card_is_gone_and_the_context_survives(
        self, monkeypatch, client_with_everything
    ):
        """Se llamaba `test_the_card_stays_when_the_provider_is_down` y defendía
        el cambio de `{% if weather %}` a `{% if weather_card %}`: la tarjeta era
        también el control, así que esconderla porque el proveedor no respondía
        dejaba sin forma de elegir otra ubicación.

        **`LV-216` retiró la tarjeta entera**, así que esa defensa ya no aplica —
        y fue justamente ese estado, "El pronóstico no está disponible por ahora",
        el que el usuario tenía en pantalla al pedir el retiro.

        `weather_card` sigue calculándose y sigue siendo `True` con el proveedor
        caído: es la decisión de `R8.4` intacta, y lo que permite reponer la
        tarjeta recuperando el bloque de git.
        """
        monkeypatch.setattr(
            "apps.core.weather.forecast_for", lambda *args, **kwargs: None
        )
        _fleet()
        _permission(_cc("CC738"))

        response = _panel(client_with_everything)

        assert response.context["weather"] is None
        assert response.context["weather_card"] is True
        assert "EL CLIMA" not in response.content.decode().upper()

    def test_the_card_is_absent_when_there_is_no_location_at_all(
        self, asked, client_with_everything
    ):
        _cc("CC738")

        response = _panel(client_with_everything)

        assert response.context["weather_card"] is False
        assert asked == []

    def test_no_inline_javascript_was_added(self, asked, client_with_everything):
        _permission(_cc("CC738"))

        content = _panel(client_with_everything).content.decode()

        assert "onchange" not in content
        assert "data-autosubmit" in content
