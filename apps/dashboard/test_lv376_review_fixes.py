"""LV-376: dos defectos que halló la revisión independiente de Cumplimiento v4.

1. Un permiso vigente que vence en 30 días o menos y que YA tiene su renovación solicitada no ofrece el
   enlace «Renovar» (terminaba en «ya fue renovado») ni dice «renovar ahora»: dice que la renovación
   está pedida.
2. «Faenas sin permiso» cuenta sólo las faenas sin solicitud ni permiso; las que esperan a la DGAC van en
   su tarjeta. Tarjeta, tira y tabla coinciden con un mundo mixto, y cada faena cuenta en una sola tarjeta.
"""

# ruff: noqa: F811
from datetime import timedelta

import pytest
from django.utils import translation

from apps.core.testing import login_as as _login_as
from apps.dashboard.test_lv359_compliance_permits import (
    TODAY,
    VIEW,
    _page,
    _permit,
    _site,
)
from apps.operations.models import FlightPermission

ADD = "add_flightpermission"
GEO = "add_geoplan"


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


def login_as(*codenames, **kwargs):
    client = _login_as(*codenames, **kwargs)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


def _row(client, code):
    rows = _page(client).context["cx_permits"]["rows"]
    return next(r for r in rows if r["cost_center"].code == code)


@pytest.mark.django_db
def test_an_already_requested_renewal_offers_no_renew_link():
    site = _site("CC1")
    current = _permit(site, 12, number="P-1")
    FlightPermission.objects.create(
        cost_center=site,
        renews=current,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Sector",
        area_type="unpopulated",
        valid_from=TODAY + timedelta(days=13),
        valid_until=TODAY + timedelta(days=100),
    )
    assert current.active_renewal is not None
    client = login_as(VIEW, ADD, GEO)
    action = _row(client, "CC1")["action"]
    assert action["url"] == ""
    assert "renew now" not in action["text"]
    assert "already requested" in action["text"]


@pytest.mark.django_db
def test_without_a_renewal_the_link_and_the_phrase_remain():
    site = _site("CC1")
    current = _permit(site, 12, number="P-1")
    action = _row(login_as(VIEW, ADD, GEO), "CC1")["action"]
    assert action["url"].endswith(f"renueva={current.pk}")
    assert "renew now" in action["text"]


@pytest.mark.django_db
def test_cards_strip_and_table_agree_in_a_mixed_world():
    in_force, waiting, not_started, nothing = (
        _site(code) for code in ("CC1", "CC2", "CC3", "CC4")
    )
    _permit(in_force, 200)
    _permit(waiting, 30, status=FlightPermission.STATUS_REQUESTED)
    FlightPermission.objects.create(
        cost_center=not_started,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        location="Sector",
        area_type="unpopulated",
        valid_from=TODAY + timedelta(days=10),
        valid_until=TODAY + timedelta(days=90),
    )
    client = login_as(VIEW)
    context = _page(client).context
    permits = context["cx_permits"]
    cards = {c["key"]: c["n"] for c in context["cx_cards"]}
    tally = {t["key"]: t["n"] for t in permits["tally"]}
    assert permits["total"] == 4
    # cada faena cuenta en UNA tarjeta
    assert cards["no_permit"] == tally["none"] == 1  # CC4
    assert cards["waiting"] == tally["waiting"] == 2  # CC2 y CC3
    assert cards["no_permit"] + cards["waiting"] + tally["ok"] == permits["total"]
    rows_none = [r for r in permits["rows"] if r["kind"] == "none"]
    assert len(rows_none) == cards["no_permit"]
    # el título de la tabla dice «sin permiso vigente»: ahí sí entran las que esperan
    assert permits["without_permit"] == cards["no_permit"] + cards["waiting"] == 3
    assert "3 without a permit in force" in permits["title"]
