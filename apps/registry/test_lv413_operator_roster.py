"""LV-413: búsqueda, filtros, semáforo y camino de vuelta en el padrón de operadores.

Pedido del usuario: «he tenido problemas con el filtro y cómo navegar en los operadores».
La lista sólo buscaba por nombre, RUT tal cual y credencial; tenía un único filtro de estado;
pintaba en ámbar toda credencial con fecha futura (también una de 2029), y la ficha no volvía
a la búsqueda de donde se vino.

Las afirmaciones de presentación comparan contra el objeto (`CREDENTIAL_BAND_CSS`) y se acotan
al cuerpo de la tabla, porque el armazón de la página comparte vocabulario con las filas
(lección de LV-118). Datos ficticios.
"""

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import CostCenter, Operator
from apps.registry.selectors import (
    CREDENTIAL_BAND_CSS,
    authorization_items,
    credential_band,
)

URL = reverse("operator-list")
VIEW = "view_operator"


def _today():
    return timezone.localdate()


def _op(name, **extra):
    extra.setdefault("employee_id", f"E-{name}")
    return Operator.objects.create(full_name=name, **extra)


def _pdf(operator):
    doc_type, _ = DocumentType.objects.get_or_create(
        code="dgac-credential", defaults={"name": "Credencial DGAC"}
    )
    return Document.objects.create(
        title="Credencial DGAC",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=operator.pk,
        file_path="cred.pdf",
        issue_date=date(2026, 1, 1),
    )


def _names(response):
    return {o.full_name for o in response.context["objects"]}


def _rows(response):
    return response.content.decode().split('id="table-body"')[-1]


@pytest.fixture
def roster(db):
    today = _today()
    cc = CostCenter.objects.create(code="CC738", name="Faena Norte")
    other_cc = CostCenter.objects.create(code="CC21", name="Faena Sur")
    people = {
        "vencida": _op(
            "Ana Vencida",
            rut="11111111-1",
            dgac_credential="4021",
            credential_expiry=today - timedelta(days=3),
            cost_center=cc,
            authorizations="MAVIC - PHANTOM",
        ),
        "pronto": _op(
            "Bruno Pronto",
            rut="12.345.678-5",
            dgac_credential="5133",
            credential_expiry=today + timedelta(days=10),
            cost_center=cc,
            authorizations="MATRICE-ELIOS, MAVIC",
        ),
        "medio": _op(
            "Carla Medio",
            credential_expiry=today + timedelta(days=45),
            cost_center=other_cc,
            authorizations="Multirotor hasta 25 kg",
        ),
        "vigente": _op(
            "Diego Vigente",
            credential_expiry=today + timedelta(days=900),
        ),
        "sinfecha": _op("Elena Sinfecha"),
    }
    _pdf(people["vigente"])
    return people


@pytest.mark.django_db
class TestSearch:
    @pytest.mark.parametrize("text", ["12.345.678-5", "12345678-5", "123456785"])
    def test_rut_with_or_without_format(self, roster, text):
        response = login_as(VIEW).get(URL, {"q": text})
        assert _names(response) == {"Bruno Pronto"}

    def test_rut_stored_canonical_found_with_dots(self, roster):
        response = login_as(VIEW).get(URL, {"q": "11.111.111-1"})
        assert _names(response) == {"Ana Vencida"}

    def test_by_credential_number(self, roster):
        assert _names(login_as(VIEW).get(URL, {"q": "5133"})) == {"Bruno Pronto"}

    def test_by_cost_center_code_and_name(self, roster):
        client = login_as(VIEW)
        assert _names(client.get(URL, {"q": "CC21"})) == {"Carla Medio"}
        assert _names(client.get(URL, {"q": "faena norte"})) == {
            "Ana Vencida",
            "Bruno Pronto",
        }

    def test_by_qualification_text(self, roster):
        assert _names(login_as(VIEW).get(URL, {"q": "elios"})) == {"Bruno Pronto"}

    def test_the_placeholder_names_what_it_searches(self, roster):
        content = login_as(VIEW).get(URL).content.decode()
        assert gettext("Name, RUT, credential, cost center or model…") in content


@pytest.mark.django_db
class TestFilters:
    @pytest.mark.parametrize(
        "key, expected",
        [
            ("lapsed", {"Ana Vencida"}),
            ("soon", {"Bruno Pronto"}),
            ("warning", {"Carla Medio"}),
            ("current", {"Diego Vigente"}),
            ("missing", {"Elena Sinfecha"}),
            ("attention", {"Ana Vencida", "Elena Sinfecha"}),
        ],
    )
    def test_credential_band(self, roster, key, expected):
        assert _names(login_as(VIEW).get(URL, {"credential": key})) == expected

    def test_pdf_yes_and_no(self, roster):
        client = login_as(VIEW)
        assert _names(client.get(URL, {"pdf": "yes"})) == {"Diego Vigente"}
        assert "Diego Vigente" not in _names(client.get(URL, {"pdf": "no"}))
        assert len(_names(client.get(URL, {"pdf": "no"}))) == 4

    def test_cost_center_and_unassigned(self, roster):
        client = login_as(VIEW)
        cc = CostCenter.objects.get(code="CC21")
        assert _names(client.get(URL, {"cost_center": cc.pk})) == {"Carla Medio"}
        assert _names(client.get(URL, {"cost_center": "none"})) == {
            "Diego Vigente",
            "Elena Sinfecha",
        }
        # Un valor malformado no revienta: lista vacía.
        assert client.get(URL, {"cost_center": "nope"}).status_code == 200

    def test_qualified_for_model(self, roster):
        assert _names(login_as(VIEW).get(URL, {"model": "MAVIC"})) == {
            "Ana Vencida",
            "Bruno Pronto",
        }

    def test_filters_combine(self, roster):
        client = login_as(VIEW)
        response = client.get(
            URL, {"model": "MAVIC", "credential": "soon", "pdf": "no"}
        )
        assert _names(response) == {"Bruno Pronto"}
        response = client.get(URL, {"model": "MAVIC", "q": "ana"})
        assert _names(response) == {"Ana Vencida"}

    def test_the_model_options_come_from_the_dgac_text(self, roster):
        options = login_as(VIEW).get(URL).context["model_options"]
        assert "MATRICE-ELIOS" in options
        assert options.count("MAVIC") == 1

    def test_status_filter_still_works(self, roster):
        roster["sinfecha"].is_active = False
        roster["sinfecha"].save()
        names = _names(login_as(VIEW).get(URL, {"is_active": "archived"}))
        assert names == {"Elena Sinfecha"}


@pytest.mark.django_db
class TestQuickFilters:
    def _chips(self, response):
        return {chip["label"]: chip for chip in response.context["quick_filters"]}

    def test_counts_match_the_rows_the_click_brings(self, roster):
        client = login_as(VIEW)
        chips = self._chips(client.get(URL))
        for chip in chips.values():
            target = client.get(URL + chip["url"])
            assert chip["count"] == len(target.context["objects"]), chip["label"]
        assert chips[gettext("Credential lapsed")]["count"] == 1
        assert chips[gettext("No cost center")]["count"] == 2

    def test_counts_follow_the_other_filters_and_toggle_off(self, roster):
        client = login_as(VIEW)
        chips = self._chips(client.get(URL, {"q": "faena norte"}))
        assert chips[gettext("No PDF")]["count"] == 2
        assert chips[gettext("No cost center")]["count"] == 0
        on = self._chips(client.get(URL, {"pdf": "no"}))[gettext("No PDF")]
        assert on["active"] is True
        assert "pdf" not in parse_qs(urlparse(on["url"]).query)


@pytest.mark.django_db
class TestFiltersSurviveNavigation:
    def test_htmx_page_keeps_filters_and_uses_operator_rows(self, roster):
        for i in range(30):
            _op(f"Relleno {i:02d}", authorizations="MAVIC")
        response = login_as(VIEW).get(
            URL, {"model": "MAVIC", "page": 2}, HTTP_HX_REQUEST="true"
        )
        assert response.templates[0].name == "registry/_operator_rows.html"
        content = response.content.decode()
        # La paginación fuera de banda lleva el filtro en sus enlaces.
        pager = content.split('id="pagination-container"')[-1]
        assert "model=MAVIC" in pager
        # Y los atajos viajan fuera de banda con el conteo del filtro puesto.
        assert 'id="op-quick"' in content and 'hx-swap-oob="true"' in content
        assert len(response.context["objects"]) == 32 - 25

    def test_sort_links_keep_filters(self, roster):
        content = login_as(VIEW).get(URL, {"credential": "soon"}).content.decode()
        assert "?credential=soon&amp;sort=name" in content

    def test_the_row_carries_the_list_query_and_the_ficha_goes_back(self, roster):
        client = login_as(VIEW)
        response = client.get(URL, {"credential": "soon", "page": "1"})
        rows = _rows(response)
        pk = roster["pronto"].pk
        assert f"{pk}/?back=credential%3Dsoon%26page%3D1" in rows
        detail = client.get(
            reverse("operator-detail", args=[pk]), {"back": "credential=soon&page=1"}
        )
        assert detail.context["list_url"] == f"{URL}?credential=soon&page=1"

    def test_back_cannot_leave_the_list(self, roster):
        detail = login_as(VIEW).get(
            reverse("operator-detail", args=[roster["pronto"].pk]),
            {"back": "https://evil.example/?x=1"},
        )
        assert detail.context["list_url"].startswith(URL + "?")


@pytest.mark.django_db
class TestTrafficLight:
    @pytest.mark.parametrize(
        "days, band",
        [
            (-1, "lapsed"),
            (0, "soon"),
            (30, "soon"),
            (31, "warning"),
            (60, "warning"),
            (61, "current"),
            (1200, "current"),
        ],
    )
    def test_band_cuts(self, days, band):
        today = _today()
        assert credential_band(today + timedelta(days=days), today)[0] == band

    def test_no_date_is_missing_not_ok(self):
        assert credential_band(None, _today()) == ("missing", None)

    @pytest.mark.parametrize(
        "key, band",
        [
            ("vencida", "lapsed"),
            ("pronto", "soon"),
            ("medio", "warning"),
            ("vigente", "current"),
            ("sinfecha", "missing"),
        ],
    )
    def test_each_row_carries_its_band_class(self, roster, key, band):
        response = login_as(VIEW).get(URL, {"q": roster[key].full_name})
        rows = _rows(response)
        assert f'class="badge {CREDENTIAL_BAND_CSS[band]}"' in rows
        others = set(CREDENTIAL_BAND_CSS.values()) - {CREDENTIAL_BAND_CSS[band]}
        for css in others:
            assert f'class="badge {css}"' not in rows

    def test_a_far_expiry_is_never_amber(self, roster):
        rows = _rows(login_as(VIEW).get(URL, {"q": "Diego"}))
        assert "badge sev-caution" not in rows
        assert "badge sev-warning" not in rows

    def test_every_band_class_has_a_style(self):
        css = "".join(
            (Path(settings.BASE_DIR) / "static" / "css" / name).read_text("utf-8")
            for name in ("app.css", "expiry-band.css")
        )
        for name in CREDENTIAL_BAND_CSS.values():
            assert f".badge.{name}" in css, name


@pytest.mark.django_db
class TestCells:
    def test_pdf_cell_links_to_the_credential(self, roster):
        doc = Document.objects.get(object_id=roster["vigente"].pk)
        client = login_as(VIEW, "view_document")
        rows = _rows(client.get(URL, {"q": "Diego"}))
        assert reverse("document-detail", args=[doc.pk]) in rows

    def test_pdf_cell_without_document_permission_does_not_link(self, roster):
        doc = Document.objects.get(object_id=roster["vigente"].pk)
        rows = _rows(login_as(VIEW).get(URL, {"q": "Diego"}))
        assert reverse("document-detail", args=[doc.pk]) not in rows

    def test_upload_shortcut_only_with_both_permissions(self, roster):
        assert "data-credential-upload" not in _rows(
            login_as(VIEW).get(URL, {"q": "Elena"})
        )
        rows = _rows(
            login_as(VIEW, "change_operator", "add_document").get(URL, {"q": "Elena"})
        )
        assert "data-credential-upload" in rows
        assert "#credential-upload" in rows

    def test_the_header_names_the_credential_pdf(self, roster):
        content = login_as(VIEW).get(URL).content.decode()
        assert gettext("Credential PDF") in content.split("<thead>")[1]

    def test_qualifications_as_verbatim_pieces(self, roster):
        rows = _rows(login_as(VIEW).get(URL, {"q": "Bruno"}))
        assert '<span class="op-qual">MATRICE-ELIOS</span>' in rows
        assert '<span class="op-qual">MAVIC</span>' in rows
        assert 'title="MATRICE-ELIOS, MAVIC"' in rows

    def test_authorization_items_keep_the_text(self):
        assert authorization_items("MAVIC - PHANTOM - MATRICE-ELIOS") == [
            "MAVIC",
            "PHANTOM",
            "MATRICE-ELIOS",
        ]
        assert authorization_items("") == []
        assert authorization_items("Multirotor hasta 25 kg") == [
            "Multirotor hasta 25 kg"
        ]


@pytest.mark.django_db
class TestPermissionsAndTenants:
    def test_403_without_view_operator(self, roster):
        client = login_as()
        assert client.get(URL).status_code == 403
        assert client.get(URL, HTTP_HX_REQUEST="true").status_code == 403

    def test_other_company_is_invisible_to_search_filters_and_counts(self, db):
        a = OperationalTenant.objects.create(name="A", slug="a-413")
        b = OperationalTenant.objects.create(name="B", slug="b-413")
        cc_b = CostCenter.objects.create(code="CC999", name="Faena B", tenant=b)
        _op("Propia", tenant=a)
        _op(
            "Ajena",
            tenant=b,
            cost_center=cc_b,
            rut="14141414-3",
            authorizations="SECRETO",
            credential_expiry=_today() - timedelta(days=1),
        )
        client = login_as(VIEW, member_of=a)
        assert _names(client.get(URL)) == {"Propia"}
        assert _names(client.get(URL, {"q": "14.141.414-3"})) == set()
        assert _names(client.get(URL, {"cost_center": cc_b.pk})) == set()
        response = client.get(URL)
        assert "SECRETO" not in response.context["model_options"]
        assert cc_b not in list(response.context["cost_center_options"])
        chips = {c["label"]: c["count"] for c in response.context["quick_filters"]}
        assert chips[gettext("Credential lapsed")] == 0


def _luminance(hex_color):
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(fg, bg):
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_in_force_badge_reads_at_aa(theme):
    """La insignia «vigente» usa `--id-ok-*`. `contrast.py` lo mide mal (el bloque de
    impresión de `identity.css`, ver `diseno-ui/SKILL.md`), así que se calcula acá sobre
    los dos primeros bloques que lo definen: el claro y el `[data-theme="dark"]`."""
    import re

    css = (Path(settings.BASE_DIR) / "static" / "css" / "identity.css").read_text(
        "utf-8"
    )
    blocks = re.findall(
        r"--id-ok-bg:\s*(#[0-9a-f]{6});[^}]*?--id-ok-text:\s*(#[0-9a-f]{6})", css
    )
    bg, fg = blocks[0] if theme == "light" else blocks[1]
    assert _ratio(fg, bg) >= 4.5
