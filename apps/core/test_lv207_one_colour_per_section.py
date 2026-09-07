"""LV-207: un color por sección del menú, y ocho secciones distinguibles.

Pedido del usuario con captura: *"panel lateral, los colores por región
mantenerlos separados, con cada uno para ser diferentes, no mezclar"*.

La clase de color se asignaba por **la app a la que apunta cada fila**, no por la
sección en que está, así que el color no agrupaba ni distinguía: **Informes**
mezclaba azul y ámbar adentro, **Inventario** mezclaba azul y gris, y tres
secciones compartían el azul.

⚠️ **Este archivo también deja constancia de que el contraste NO era el
problema.** El diagnóstico registrado en la fila afirmaba que cinco de los siete
colores no llegaban a 3:1 en tema claro, con cifras como `registry 2.41`. Es
falso: calculado sobre los hex del CSS contra `--ac-surface`, `registry` da
**5.91**. Aquellos números se midieron contra el fondo equivocado, y por eso los
ratios de acá se **calculan** en vez de leerse de un navegador.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import login_as

CSS = Path("static/css/app.css")
TEMPLATE = Path("templates/base.html")
LIGHT_SURFACE = "#ffffff"
DARK_SURFACE = "#161f2d"
# WCAG 1.4.11: un icono es un elemento gráfico, no texto. Mismo umbral que LV-185.
GRAPHIC_MIN = 3.0


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb):
    def channel(value):
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground, background):
    l1, l2 = _luminance(_rgb(foreground)), _luminance(_rgb(background))
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


def _icon_colours(dark=False):
    """Los colores de icono declarados, por familia, leídos del CSS."""
    prefix = r'\[data-theme="dark"\] ' if dark else ""
    pattern = re.compile(
        prefix + r"\.nav-([a-z]+) \.nav-icon \{ color: (#[0-9a-f]{6}); \}"
    )
    css = CSS.read_text(encoding="utf-8")
    found = {}
    for line in css.splitlines():
        # Las reglas del tema oscuro también casarían el patrón claro, así que se
        # descarta por la forma de la línea y no por el orden en el archivo.
        if not dark and line.strip().startswith("[data-theme"):
            continue
        match = pattern.search(line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def _sections_with_their_classes():
    """Por cada sección del menú, el conjunto de clases de color que usa.

    Recorre el HTML llevando la cuenta de los `<div>` para saber cuándo termina un
    `nav-group-items`: los ítems de fuera de los grupos (Panel arriba,
    Administración abajo) no pertenecen a ninguna sección.

    ⚠️ **Los `{% comment %}` se blanquean antes de escanear.** El menú lleva
    cinco enlaces comentados —los retiros de `LV-D8`, `R5.8`, `LV-69`, `LV-103`
    y `LV-150`— que este escaneo contaba como si se dibujaran. Hoy no cambia
    ningún veredicto, porque cada uno usa la clase de su propio grupo; pero un
    ítem comentado con otra clase habría hecho fallar el test por una fila que
    nadie ve, o —peor— habría tapado una mezcla real al aportar el color que
    faltaba. **Un test que mide una entrada distinta de la que el usuario recibe
    da su veredicto por casualidad.**

    Se reutiliza el blanqueador de `test_translations`, que se escribió para
    exactamente este riesgo en `LV-169`, en vez de copiar la expresión: dos
    copias del mismo recorte es cómo una se queda vieja.
    """
    from apps.core.test_translations import _without_template_comments

    source = _without_template_comments(TEMPLATE.read_text(encoding="utf-8"))
    token = re.compile(
        r'data-nav-group="(?P<group>[^"]+)"'
        r"|(?P<open><div\b)"
        r"|(?P<close></div>)"
        r"|nav-item (?P<cls>nav-[a-z]+)"
    )
    sections, loose = {}, set()
    section, depth = None, 0
    for match in token.finditer(source):
        if match.group("group"):
            section, depth = match.group("group"), 0
        elif match.group("open") and section is not None:
            depth += 1
        elif match.group("close") and section is not None:
            depth -= 1
            if depth <= 0:
                section = None
        elif match.group("cls"):
            if match.group("cls") in NOT_A_SECTION:
                continue
            if section is None:
                loose.add(match.group("cls"))
            else:
                sections.setdefault(section, set()).add(match.group("cls"))
    return sections, loose


#: Clases `nav-*` que **no** nombran una sección del menú, y por eso no llevan
#: color propio.
#:
#: `nav-shortcut` es de `UX-31`: los atajos del rol repiten destinos que ya están
#: más abajo, cada uno en su sección y con el color de esa sección. Darles un
#: color propio habría inventado una novena sección que no existe; darles el
#: color de su destino habría puesto cuatro colores en una tira de tres
#: renglones. Se distinguen por sangría y peso, no por color — y por eso el
#: escaneo tiene que saltearlos: si no, este guardián exige un color para algo
#: cuya decisión de diseño fue justamente no tenerlo.
NOT_A_SECTION = frozenset({"nav-shortcut"})


class TestTheScanSeesWhatTheUserSees:
    """El guardián del guardián, y lo que vuelve al arreglo de arriba algo más
    que un comentario."""

    def test_the_commented_out_links_are_not_scanned(self):
        """Cinco enlaces del menú están dentro de `{% comment %}` y no se
        dibujan. Contarlos hacía que este archivo afirmara sobre filas que el
        usuario no recibe.

        Se compara el recuento crudo con el blanqueado en vez de fijar un número:
        un `assert == 23` se rompería la próxima vez que alguien agregue un ítem
        —o retire otro— por una razón que no tiene nada que ver con lo que este
        test protege.
        """
        from apps.core.test_translations import _without_template_comments

        source = TEMPLATE.read_text(encoding="utf-8")
        anchors = re.compile(r'class="nav-item (nav-[a-z]+)')
        raw = anchors.findall(source)
        live = anchors.findall(_without_template_comments(source))

        assert live, "no quedó ningún ítem de menú: ¿cambió el marcado?"
        assert len(live) < len(raw), (
            "ya no hay enlaces comentados en el menú. Si los retiros se "
            "completaron, este test sobra; si no, alguien borró el ancla en vez "
            "de comentarla y la reversión anunciada ya no se puede ejecutar."
        )


class TestOneColourPerSection:
    def test_no_section_mixes_colours_inside(self):
        """Era el defecto de la captura: Informes con azul y ámbar a la vez."""
        sections, _loose = _sections_with_their_classes()

        assert sections, "no se encontró ninguna sección: ¿cambió el marcado?"
        for name, classes in sections.items():
            assert len(classes) == 1, f"la sección '{name}' mezcla {sorted(classes)}"

    def test_no_two_sections_share_a_colour(self):
        """El otro lado del mismo defecto: tres secciones compartían el azul."""
        sections, _loose = _sections_with_their_classes()
        used = [next(iter(classes)) for classes in sections.values()]

        assert len(used) == len(set(used)), sorted(used)

    def test_the_loose_items_have_their_own_colours(self):
        """Panel y Administración están fuera de los grupos, y también se distinguen."""
        sections, loose = _sections_with_their_classes()
        de_secciones = {next(iter(c)) for c in sections.values()}

        assert loose, "no se encontraron ítems fuera de los grupos"
        assert not (loose & de_secciones), sorted(loose & de_secciones)


class TestEveryClassIsDeclaredInBothThemes:
    def test_the_css_and_the_template_cover_the_same_classes(self):
        """Una clase sin color se dibuja con el color heredado y nadie lo nota."""
        sections, loose = _sections_with_their_classes()
        en_plantilla = {next(iter(c)) for c in sections.values()} | loose
        en_css = {f"nav-{name}" for name in _icon_colours()}

        assert en_plantilla == en_css

    def test_the_dark_theme_covers_the_same_classes(self):
        assert set(_icon_colours()) == set(_icon_colours(dark=True))


class TestTheContrastIsCalculatedNotAssumed:
    @pytest.mark.parametrize("dark", [False, True])
    def test_every_icon_clears_three_to_one(self, dark):
        """WCAG 1.4.11 para elementos gráficos, en los dos temas.

        **Se calcula acá y no se lee de un navegador**: el diagnóstico previo de
        esta fila reportó cinco fallas que no existen, por medir contra el fondo
        equivocado. Un ratio es aritmética sobre dos hex, y el CSS los tiene.
        """
        surface = DARK_SURFACE if dark else LIGHT_SURFACE

        for family, colour in _icon_colours(dark=dark).items():
            ratio = contrast(colour, surface)
            assert ratio >= GRAPHIC_MIN, (
                f"nav-{family}: {colour} da {ratio} sobre {surface}"
            )

    def test_the_registry_blue_was_never_the_problem(self):
        """La cifra concreta que el diagnóstico previo dio por mala.

        Decía `registry 2.41`. Este test fija el valor real para que nadie vuelva
        a "corregir" un color que cumple de sobra.
        """
        assert contrast(_icon_colours()["registry"], LIGHT_SURFACE) > 5

    def test_the_new_green_was_chosen_by_measurement(self):
        """`#65a30d`, el candidato del diagnóstico previo, daba 3.09 en claro.

        Pasaba por nueve centésimas. El elegido da más de 4.5, así que un ajuste
        de fondo no lo deja fuera de norma.
        """
        assert contrast(_icon_colours()["flight"], LIGHT_SURFACE) > 4.5


class TestTheScreenRendersThem:
    @pytest.mark.django_db
    def test_the_menu_uses_the_section_classes(self, db):
        body = login_as().get(reverse("dashboard")).content.decode()

        for family in ("nav-flight", "nav-reports", "nav-inventory"):
            assert family in body

    @pytest.mark.django_db
    def test_the_retired_classes_are_gone(self, db):
        """`nav-operations` y `nav-workboard` ya no se usan.

        Sus colores se reciclaron (el teal a Inventario, el magenta a Informes),
        y dejar las clases vivas invitaría a volver a asignarlas por app.
        """
        body = login_as().get(reverse("dashboard")).content.decode()

        assert "nav-operations" not in body
        assert "nav-workboard" not in body
