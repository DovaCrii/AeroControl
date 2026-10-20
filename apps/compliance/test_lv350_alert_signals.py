"""LV-350: legibilidad y señales en alertas y bandeja.

El usuario se quejó de mensajes en gris que pasan desapercibidos. Tres garantías:

1. **La gravedad de la fila se lee sin color**: el chip de vencimiento lleva símbolo + texto, y
   «Sin asignar» (la ausencia de dueño es el hecho que hay que ver) lleva símbolo + texto + tono de aviso.
2. **Los vacíos dicen qué pasó y qué hacer** (LV-328), y las ayudas en gris pasan a las señales de E5.
3. **Cada par de colores nuevo llega a 4,5:1**, calculado con los tokens del CSS, en claro y oscuro.
"""

# ruff: noqa: F811
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils.translation import gettext

from apps.compliance.digest import BUCKET_BADGE_CSS
from apps.compliance.models import Alert
from apps.compliance.test_lv118_alert_tray_hygiene import (  # noqa: F401
    TODAY,
    _alert,
    _client,
    aircraft,
    cost_center,
    rule,
)
from apps.dashboard.test_lv312_hero import _contrast, _luminance, _tokens

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
SYMBOL = "id-signal-icon"


def _rows(response):
    return response.content.decode().split('id="table-body"', 1)[-1]


def _row_of(body, alert):
    return re.search(rf'<tr data-pk="{alert.pk}".*?</tr>', body, re.S).group(0)


@pytest.mark.django_db
class TestSeverityReadsWithoutColour:
    def test_an_overdue_row_has_symbol_and_text_in_its_chip(self, rule, aircraft):
        alert = _alert(rule, aircraft, watched_value=str(TODAY - timedelta(days=12)))

        row = _row_of(_rows(_client().get(reverse("alert-list"))), alert)
        chip = re.search(
            r'<span class="badge al-sev.*?</span></span>', row, re.S
        ).group(0)

        assert BUCKET_BADGE_CSS["overdue"] in chip
        assert SYMBOL in chip, "la fila vencida perdió su símbolo"
        assert gettext("Overdue") in chip

    def test_a_later_row_gets_its_own_calmer_symbol(self, rule, aircraft):
        alert = _alert(rule, aircraft, watched_value=str(TODAY + timedelta(days=200)))

        row = _row_of(_rows(_client().get(reverse("alert-list"))), alert)

        chip = re.search(
            r'<span class="badge al-sev.*?</span></span>', row, re.S
        ).group(0)

        assert 'data-al-level="nominal"' in chip
        assert SYMBOL in chip and gettext("Due") in chip
        # el triángulo es de lo que avisa, no de lo lejano
        assert "M12 3.5 2.8 19.5" not in chip

    def test_unassigned_says_it_with_symbol_and_text(self, rule, aircraft):
        _alert(rule, aircraft, watched_value="x")
        assert Alert.objects.filter(assigned_to__isnull=True).exists()

        body = _rows(_client().get(reverse("alert-list")))
        flag = re.search(r'<span class="al-flag">.*?</span>', body, re.S).group(0)

        assert SYMBOL in flag and gettext("Unassigned") in flag

    def test_the_resolution_reason_is_a_signal_not_grey_fine_print(
        self, rule, aircraft
    ):
        _alert(rule, aircraft, watched_value="x", resolved=True)

        body = _rows(_client().get(reverse("alert-list"), {"is_resolved": "true"}))
        reason = re.search(
            r'<div class="mt-1 alert-reason">.*?</div>\s*</div>', body, re.S
        ).group(0)

        assert "id-hint" in reason and SYMBOL in reason
        assert "Se actualiza el seguro" in reason
        assert "text-body-secondary" not in reason


@pytest.mark.django_db
class TestEmptyStatesSayWhatToDo:
    def test_nothing_pending_offers_the_resolved_ones(self):
        body = _rows(_client().get(reverse("alert-list")))

        assert 'class="empty-state__title' in body
        assert gettext("Nothing pending.") in body
        assert 'class="btn btn-outline-secondary"' in body
        assert gettext("See the resolved ones") in body

    def test_a_filtered_empty_offers_a_primary_clear_button(self):
        body = _rows(_client().get(reverse("alert-list"), {"q": "zzz-nada"}))

        assert gettext("No alerts match the current filters.") in body
        assert re.search(r'class="btn btn-primary">' + gettext("Clear filters"), body)

    def test_no_tasks_found_offers_the_board(self, db):
        user = User.objects.create_user("wb", "wb@test.com", "password")
        user.user_permissions.add(Permission.objects.get(codename="view_kanbantask"))
        client = Client()
        client.login(username="wb", password="password")

        body = client.get(reverse("workboard-list")).content.decode()

        assert gettext("No tasks found.") in body
        assert reverse("kanban") in body and gettext("Open the board") in body


def _hex(name, which):
    found = re.findall(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", APP_CSS)
    assert len(found) >= 2, name
    return found[which]


@pytest.mark.parametrize("theme", ["light", "dark"])
class TestEveryNewPairReaches45:
    def test_severity_chips_and_the_unassigned_flag(self, theme):
        which = 0 if theme == "light" else 1
        for level in ("critical", "warning", "caution", "advisory", "nominal"):
            text = _hex(f"sev-{level}-text", which)
            bg = _hex(f"sev-{level}-bg", which)
            ratio = _contrast(_luminance(text), _luminance(bg))
            assert ratio >= 4.5, (theme, level, ratio)

    def test_the_grey_helpers_on_the_surface(self, theme):
        tokens = _tokens(theme)
        for name in ("text-secondary", "text"):
            ratio = _contrast(_luminance(tokens[name]), _luminance(tokens["surface"]))
            assert ratio >= 4.5, (theme, name, ratio)


class TestTheLayerStaysInItsLane:
    def _e6(self):
        start = IDENTITY.index("/* E6: alertas y bandeja")
        end = IDENTITY.index("/* == F:", start)
        return IDENTITY[start:end]

    def test_e6_sits_after_e5_and_before_f(self):
        assert IDENTITY.index("/* E5: señales") < IDENTITY.index(
            "/* E6: alertas y bandeja"
        )
        assert "animation" not in self._e6() and "@keyframes" not in self._e6()

    def test_e6_adds_no_colour_of_its_own(self):
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", self._e6()), "E6 sólo lee tokens"
