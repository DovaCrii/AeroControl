"""LV-149: el encabezado de la ficha del plan y la hoja de campo para SIGO.

Los tres avisos de honestidad se fijan **primero**, porque son la regresión más
probable de un rediseño: la tarjeta pasa a tener dos formas y un aviso que
existía en la única forma anterior puede quedarse en una de las dos sin que nada
falle.
"""

import math
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.registry.models import CostCenter
from .kml.canonical import empty_document, new_uid
from .models import GeoPlan, GeoPlanVersion
from .views import GEO_SOURCE_DOC_TYPE_CODE, GEO_SOURCE_DOC_TYPE_NAME

DETAIL = Path(settings.BASE_DIR) / "templates" / "geo" / "plan_detail.html"
SHEET = Path(settings.BASE_DIR) / "templates" / "geo" / "_sigo_sheet.html"

# Los tres avisos, palabra por palabra como están en el catálogo de origen.
NOTICES = [
    (
        "The aerodrome is proposed by distance, among those with coordinates on "
        "file — confirm it against the AIP chart before filing."
    ),
    (
        "The commune, province and region come from the BCN administrative "
        "boundaries, which that institution publishes as referential: near a "
        "boundary the answer may be the neighbouring commune. Confirm it before "
        "filing."
    ),
    (
        "When the drawn area is not a circle, the row shows the smallest circle "
        "that covers it: SIGO accepts one circle per request, and the average "
        "radius of a non-circle is not a figure to file."
    ),
]

# Cerca del área real de CC 738 (Los Pelambres), donde la capa de BCN resuelve
# Salamanca / Choapa / Coquimbo: así la casilla de comuna de la hoja lleva un
# valor real y no un guion, que es el caso que no ejercita nada.
LAT, LON = -31.918, -70.949


def _circle(name, dlat=0.0, dlon=0.0, points=24, radius_deg=0.005):
    """Un anillo casi circular, para que la fila **no** sea la envolvente.

    Un cuadrado daría `is_enclosing=True` y la hoja llevaría el cuarto aviso:
    la forma normal —un círculo dibujado como círculo— es la que hay que
    ejercitar acá.
    """
    ring = [
        [
            LON + dlon + radius_deg * math.cos(2 * math.pi * index / points),
            LAT + dlat + radius_deg * math.sin(2 * math.pi * index / points),
            0,
        ]
        for index in range(points)
    ]
    ring.append(list(ring[0]))
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "extended_data": None,
        "extras": [],
    }


def _document(*circles):
    """`GeoPlanVersion.content` es el documento canónico (un dict), no KML."""
    document = empty_document()
    document["children"].extend(circles)
    return document


ONE_CIRCLE = _document(_circle("CG-01"))
TWO_CIRCLES = _document(_circle("CG-01"), _circle("CG-02", dlat=0.1, dlon=0.1))


@pytest.fixture
def author(db):
    return User.objects.create_user("author", password="password")


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="Los Pelambres")


def _plan(center, author, title, file_name=None, content=ONE_CIRCLE):
    plan = GeoPlan.objects.create(title=title, cost_center=center, created_by=author)
    if content is not None:
        plan.current_version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content=content,
            content_checksum="x" * 16,
            source="import",
            feature_count=1,
            size_bytes=len(content),
            created_by=author,
        )
    if file_name:
        # LV-180: el código real es `GEO_SOURCE`, no `geo-source`. El fixture
        # llevaba el segundo desde `LV-149`, así que creaba un tipo de documento
        # que la app nunca usa — pasaba igual, porque nada acá mira el código,
        # pero un fixture que no se parece a producción es una red con un agujero
        # del tamaño exacto de lo que no comprueba.
        doc_type, _created = DocumentType.objects.get_or_create(
            code=GEO_SOURCE_DOC_TYPE_CODE,
            defaults={"name": GEO_SOURCE_DOC_TYPE_NAME, "requires_expiry": False},
        )
        plan.source_document = Document.objects.create(
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(GeoPlan),
            object_id=plan.pk,
            title=file_name,
            issue_date="2026-08-26",
            file_path="",
        )
    plan.save()
    return plan


def _reader(username="reader"):
    user = User.objects.create_user(username, password="password")
    for codename in ("view_geoplan", "view_costcenter"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    client = Client()
    assert client.login(username=username, password="password")
    return client


# -- los tres avisos, en las dos formas ------------------------------------


@pytest.mark.parametrize("notice", NOTICES)
def test_every_honesty_notice_survives_in_both_forms(notice):
    """El aviso del AMC se mueve de sitio (pasa a ir pegado al dato en la hoja)
    y los otros dos se duplican en las dos formas. Ninguno puede desaparecer:
    cada uno existe porque un dato propuesto se leía como confirmado."""
    detail = DETAIL.read_text(encoding="utf-8")
    sheet = SHEET.read_text(encoding="utf-8")
    # Las plantillas cortan las cadenas largas en varias líneas, así que se
    # compara sobre el texto con los saltos y la sangría colapsados.
    flat_detail = " ".join(detail.split())
    flat_sheet = " ".join(sheet.split())
    flat_notice = " ".join(notice.split())

    assert flat_notice in flat_detail, "falta en la tabla"
    assert flat_notice in flat_sheet, "falta en la hoja de campo"


# -- el encabezado calculado -----------------------------------------------


def test_a_title_in_the_lv138_form_is_read_as_code_and_file(center, author):
    plan = _plan(
        center,
        author,
        "CC738 · CG-01_circunferencia_grande",
        "CG-01_circunferencia_grande.kmz",
    )

    assert plan.source_file_stem == "CG-01_circunferencia_grande"
    assert plan.heading == {
        "code": "CC738",
        "name": "CG-01_circunferencia_grande",
        "text": "",
    }
    assert plan.display_title == "CC738 · CG-01_circunferencia_grande"


def test_a_legacy_three_part_title_is_shortened_to_code_and_file(center, author):
    """La forma que traían los planes anteriores a LV-138. Contiene el nombre
    del archivo, así que las dos partes que valen se pueden extraer: faena y
    responsable ya tienen su propia columna."""
    plan = _plan(
        center,
        author,
        "CC738 - MLP · Juan Quiroz · CG-01_circunferencia_grande",
        "CG-01_circunferencia_grande.kmz",
    )

    assert plan.display_title == "CC738 · CG-01_circunferencia_grande"


def test_a_hand_written_title_is_left_alone(center, author):
    """La lección de LV-70: una pasada que "arregla títulos" borró texto que
    nadie le pidió tocar. Un título que no menciona el archivo son las palabras
    de una persona sobre el plan, y acortarlo elimina información."""
    plan = _plan(
        center, author, "Área ampliada tras la reunión con la DGAC", "CG-01.kmz"
    )

    assert plan.heading == {
        "code": "",
        "name": "",
        "text": "Área ampliada tras la reunión con la DGAC",
    }
    assert plan.display_title == "Área ampliada tras la reunión con la DGAC"


def test_a_plan_without_a_source_file_keeps_its_title(center, author):
    plan = _plan(center, author, "Plan sin archivo", file_name=None)

    assert plan.source_file_stem == ""
    assert plan.display_title == "Plan sin archivo"


def test_a_file_name_without_an_extension_is_not_truncated(center, author):
    """`rpartition` sobre "CG-01" devolvería cadena vacía como raíz; el nombre
    entero es la respuesta correcta."""
    plan = _plan(center, author, "CC738 · CG-01", "CG-01")

    assert plan.source_file_stem == "CG-01"


def test_the_stored_title_is_never_rewritten(center, author):
    """`display_title` es un cálculo. Una lectura más corta que se guarda es una
    migración de datos que nadie aprobó."""
    plan = _plan(
        center,
        author,
        "CC738 - MLP · Juan Quiroz · CG-01_circunferencia_grande",
        "CG-01_circunferencia_grande.kmz",
    )

    assert plan.display_title != plan.title
    plan.refresh_from_db()
    assert plan.title == "CC738 - MLP · Juan Quiroz · CG-01_circunferencia_grande"


# -- las dos formas de la tarjeta ------------------------------------------


@pytest.mark.django_db
def test_one_circle_gets_the_field_sheet_and_not_the_table(center, author):
    plan = _plan(center, author, "CC738 · CG-01", "CG-01.kmz", content=ONE_CIRCLE)

    body = _reader().get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    assert "Copia cada valor en su casilla de SIGO" in body
    assert "copy-btn" in body
    # La cabecera de la tabla es lo que distingue una forma de la otra.
    assert "Punto centro" not in body


@pytest.mark.django_db
def test_several_circles_keep_the_table(center, author):
    """Con cuarenta y siete filas la pregunta pasa a ser "cuál separo", y
    comparar filas es lo que una tabla hace bien."""
    plan = _plan(center, author, "CC738 · CG", "CG.kmz", content=TWO_CIRCLES)

    body = _reader().get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    # "Punto centro", como está en el catálogo: afirmar sobre el valor real
    # prueba de paso que la cabecera sigue traducida.
    assert "Punto centro" in body
    assert "Copia cada valor en su casilla de SIGO" not in body
    # El botón de copiar entra sólo en la celda de coordenadas: un botón por
    # celda serían siete por fila y la tabla dejaría de leerse.
    assert body.count("copy-btn") == 4  # dos filas x (latitud + longitud)


@pytest.mark.django_db
def test_the_seconds_are_written_with_a_dot_and_not_the_locale_comma(center, author):
    """Con el locale español `floatformat:2` escribe "4,80" y `format_dms` —que
    arma la lectura corrida en Python— escribe "4.80": dos formas del mismo
    número en la misma pantalla, y el botón copiaría la que la casilla de SIGO
    puede no aceptar. La casilla y la lectura tienen que coincidir."""
    plan = _plan(center, author, "CC738 · CG-01", "CG-01.kmz", content=ONE_CIRCLE)

    body = _reader().get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    assert 'data-copy="4.80"' in body
    assert 'data-copy="4,80"' not in body


@pytest.mark.django_db
def test_the_area_box_carries_the_circle_name(center, author):
    """El nombre del placemark **es** la casilla "Área" de SIGO (LV-141). La
    tabla lo mostraba en su columna "Circunferencia"; sin él la hoja perdía un
    dato que el formulario pide, y lo cazó
    `test_r10_plan_feeds_the_permit::test_it_shows_on_the_plan_page`."""
    plan = _plan(center, author, "CC738 · CG-01", "CG-01.kmz", content=ONE_CIRCLE)

    body = _reader().get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    assert "CG-01" in body
    assert 'data-copy="CG-01"' in body


@pytest.mark.django_db
def test_the_heading_shows_the_file_and_the_permit_is_a_link(center, author):
    plan = _plan(center, author, "CC738 · CG-01", "CG-01.kmz")

    body = _reader().get(reverse("geo-plan-detail", args=[plan.pk])).content.decode()

    assert '<h1 class="h4">CC738 · CG-01</h1>' in body
    # La tercera línea deja de repetir el `str(cost_center)` completo.
    assert "Los Pelambres" in body


# -- la CSP y el JS --------------------------------------------------------


def test_the_templates_carry_no_inline_javascript():
    """`script-src 'self'`: un `onclick=` o un `<script>` sin `src` en la
    plantilla rompe la CSP, y el botón dejaría de funcionar en producción
    mientras sigue funcionando en desarrollo."""
    import re

    for path in (
        DETAIL,
        SHEET,
        SHEET.with_name("_sigo_field.html"),
        SHEET.with_name("_sigo_copy_button.html"),
    ):
        # Los bloques `{% comment %}` no se dibujan, y el que explica esta regla
        # nombra justo lo que la regla prohíbe. Mismo criterio que el guardián de
        # iconos del menú (`test_r103_nav_icons_are_distinct`).
        markup = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
            "",
            path.read_text(encoding="utf-8"),
            flags=re.DOTALL,
        )
        assert "onclick=" not in markup, path.name
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", markup)
        assert not inline, f"{path.name}: {inline}"


def test_the_copy_script_carries_no_user_facing_text():
    """Las etiquetas viajan en `data-label-*` desde la plantilla, que es donde
    vive `{% translate %}`. Un literal en el .js queda en inglés en una interfaz
    en español y `makemessages` no lo ve."""
    source = (Path(settings.BASE_DIR) / "static" / "js" / "sigo-copy.js").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line
        for line in source.splitlines()
        if not line.strip().startswith(("//", "*", "/*"))
    )

    assert "dataset.labelCopied" in code
    assert "dataset.labelFailed" in code
    # El respaldo para cuando `navigator.clipboard` no existe: la aplicación se
    # sirve por http en la intranet, que no es contexto seguro.
    assert "execCommand" in code


# -- el listado ------------------------------------------------------------


@pytest.mark.django_db
def test_the_list_column_shows_the_file_name(center, author):
    _plan(
        center,
        author,
        "CC738 · CG-01_circunferencia_grande",
        "CG-01_circunferencia_grande.kmz",
    )

    body = _reader().get(reverse("geo-plan-list")).content.decode()

    assert "CG-01_circunferencia_grande" in body
    # El título completo ya no es la columna.
    assert "CC738 · CG-01_circunferencia_grande</span>" not in body


@pytest.mark.django_db
def test_the_list_can_be_searched_by_file_name(center, author):
    _plan(center, author, "CC738 · CG-01", "CG-01_circunferencia_grande.kmz")
    _plan(center, author, "CC738 · otro", "otro_archivo.kmz")

    body = (
        _reader()
        .get(reverse("geo-plan-list"), {"q": "circunferencia_grande"})
        .content.decode()
    )

    assert "CG-01_circunferencia_grande" in body
    assert "otro_archivo" not in body


@pytest.mark.django_db
def test_the_list_does_not_query_once_per_row_for_the_file(
    center, author, django_assert_max_num_queries
):
    for index in range(5):
        _plan(center, author, f"CC738 · f{index}", f"f{index}.kmz")
    client = _reader()

    # Sin `source_document` en el `select_related` son cinco consultas más.
    with django_assert_max_num_queries(10):
        client.get(reverse("geo-plan-list"))
