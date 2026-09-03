"""Guard the Spanish catalog against silently drifting from the source.

This drift went unnoticed for months because GNU gettext was not installed on
the development machine, so `makemessages` could not run and nothing compared
the catalog with the code. By the time it was checked, 29 strings rendered in
English inside a Spanish interface and the catalog held 26 duplicate entries
that made `msgmerge` refuse to run at all.

These tests parse the `.po` directly instead of shelling out to gettext, so they
fail on a machine that lacks the tooling -- which is exactly the machine where
the drift happens.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

PO_PATH = Path(settings.BASE_DIR) / "locale" / "es" / "LC_MESSAGES" / "django.po"

# Literal in a .po file, honouring escaped quotes. Two forms: the capturing one
# extracts the text, the non-capturing one is safe to nest inside a larger
# pattern without turning findall results into tuples.
#
# **Double quotes only, and that is not an oversight**: a `.po` file quotes with
# `"` and nothing else, so widening these would make the catalog parser accept a
# file gettext itself would reject. The source side has its own pair below.
_LITERAL = r'"((?:[^"\\]|\\.)*)"'
_LITERAL_NC = r'"(?:[^"\\]|\\.)*"'

# Literal in *source*, where Python and the Django template language both accept
# either quote style. Kept separate from the `.po` pair above rather than
# widening it, which is what the 2026-08-26 blind spot came down to: every
# `_SOURCE_PATTERNS` entry was built on the `.po` literal, so
# `{% translate 'Text' %}` was invisible to the whole file. Seventy-two of those
# existed in the templates at the time -- typically inside an HTML attribute,
# where double quotes would have to be escaped by eye -- and each one could be
# missing from the catalog, render in English inside the Spanish interface, and
# fail nothing.
_SRC_LITERAL_NC = r"(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')"
# Two capture groups, one per quote style: exactly one matches, and `_literals`
# below picks whichever it is. An alternation with a backreference would need
# only one group but reads like a puzzle for no gain.
_SRC_LITERAL = r"\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'"

# Strings marked for translation in Python and in templates. The Python pattern
# takes one or more adjacent literals, because a long message is usually split
# over several lines and Python joins them before gettext ever sees it.
#
# `pgettext` needs its own pattern: its first argument is the *context*, not a
# translatable string. Without this the plain pattern matched the "gettext_lazy"
# tail inside "pgettext_lazy" and reported the context as a missing msgid --
# which is what happened the first time a pgettext call was added in Python
# (the template form, `{% translate "X" context "..." %}`, never had the problem
# because the context sits after the string there).
#
# The leading `\b` on the plain pattern is what keeps it from matching inside
# `pgettext_lazy` in the first place.
_SOURCE_PATTERNS = [
    re.compile(r"\b(?:_|gettext|gettext_lazy)\(\s*((?:" + _SRC_LITERAL_NC + r"\s*)+)"),
    re.compile(
        r"\bpgettext(?:_lazy)?\(\s*"
        + _SRC_LITERAL_NC
        + r"\s*,\s*((?:"
        + _SRC_LITERAL_NC
        + r"\s*)+)"
    ),
    re.compile(r"\{%\s*(?:translate|trans)\s+(" + _SRC_LITERAL_NC + r")"),
]


def _unescape(value):
    # `\'` is source-only: a `.po` never needs it, since it quotes with `"`.
    return value.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def _literals(text):
    """Every string literal in `text`, either quote style, unescaped.

    Adjacent literals are returned in order so the caller can join them, which
    is what Python does with `_("a" "b")` before gettext ever sees it.
    """
    return [
        _unescape(double or single) for double, single in re.findall(_SRC_LITERAL, text)
    ]


def _marked_literals(content):
    """The literals `content` asks gettext to translate, with their offsets.

    Split out of `_source_strings` so the guard-of-the-guard below can drive the
    **same** scan over a handful of one-line fixtures. Asserting on a copy of
    this loop would let the copy stay right while this one drifted, which is the
    shape of the bug it exists to prevent.
    """
    for pattern in _SOURCE_PATTERNS:
        for match in pattern.finditer(content):
            yield match.start(), "".join(_literals(match.group(1)))


def _entries():
    """Yield (msgctxt, msgid, msgstr, is_fuzzy) for every entry in the catalog.

    The context matters: gettext keys entries on the (msgctxt, msgid) pair, so
    the same source literal may legitimately appear twice under different
    contexts -- which is the point of `{% translate "X" context "..." %}`.
    Reading only the msgid made such a pair look like a duplicate.
    """
    text = PO_PATH.read_text(encoding="utf-8")
    for block in re.split(r"\n\s*\n", text):
        ids = re.findall(r"(?m)^msgid ((?:" + _LITERAL_NC + r"\s*)+)", block)
        strs = re.findall(
            r"(?m)^msgstr(?:\[\d\])? ((?:" + _LITERAL_NC + r"\s*)+)", block
        )
        if not ids or not strs:
            continue
        msgid = _unescape("".join(re.findall(_LITERAL, ids[0])))
        if not msgid:  # the header entry
            continue
        ctxts = re.findall(r"(?m)^msgctxt ((?:" + _LITERAL_NC + r"\s*)+)", block)
        msgctxt = _unescape("".join(re.findall(_LITERAL, ctxts[0]))) if ctxts else ""
        msgstr = _unescape("".join(re.findall(_LITERAL, strs[0])))
        yield msgctxt, msgid, msgstr, "#, fuzzy" in block


_TEMPLATE_COMMENT = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)


def _without_template_comments(content):
    """`{% comment %}` blocks blanked out, **keeping every offset**.

    LV-169: `makemessages` no extrae de dentro de un `{% comment %}`, así que una
    cadena ahí adentro **no puede** estar en el catálogo: en cuanto alguien
    regenera, gettext la manda a obsoleta. Este guardián la exigía igual, y con
    eso le pedía al catálogo algo que el propio extractor de Django se niega a
    poner. Quedó latente desde `LV-150`, que sacó "Solicitudes SIGO" del menú
    envolviéndola en `{% comment %}` sin borrar nada: el gate siguió verde
    porque nadie corrió `makemessages` en el medio, y estalló en la primera
    regeneración. Un guardián que sólo pasa mientras no se use el flujo
    documentado no está vigilando, está esperando.

    Se reemplaza por espacios en vez de recortar para que los números de línea
    que este archivo reporta sigan apuntando al lugar real.

    `UX-09b`: el recorte se fue a `apps.core.testing` cuando fue el **tercer**
    guardián que lo necesitaba —éste, el de `scope` y el de `UX-07`— y las tres
    veces por el mismo tropiezo: alguien documenta una decisión nombrando la
    etiqueta de la que habla y el guardián lo trata como código.
    """
    from apps.core.testing import without_template_comments

    return without_template_comments(content)


def _source_strings():
    """Every literal the code asks gettext to translate, with where it came from."""
    root = Path(settings.BASE_DIR)
    found = {}
    paths = list((root / "apps").rglob("*.py")) + list(
        (root / "templates").rglob("*.html")
    )
    for path in paths:
        if "migrations" in path.parts or path.name.startswith("test"):
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".html":
            content = _without_template_comments(content)
        for offset, literal in _marked_literals(content):
            line = content.count("\n", 0, offset) + 1
            found.setdefault(literal, f"{path.relative_to(root).as_posix()}:{line}")
    return found


@pytest.fixture(scope="module")
def catalog():
    return list(_entries())


@pytest.mark.parametrize(
    "source, expected",
    [
        # Las cuatro formas, con las dos comillas cada una. Las de comillas
        # simples son las que el guardián no veía hasta el 2026-08-26.
        ('{% translate "Double in a template" %}', "Double in a template"),
        ("{% translate 'Single in a template' %}", "Single in a template"),
        ('{% trans "Old double form" %}', "Old double form"),
        ("{% trans 'Old single form' %}", "Old single form"),
        ('_("Double in python")', "Double in python"),
        ("_('Single in python')", "Single in python"),
        ('gettext_lazy("Lazy double")', "Lazy double"),
        ("gettext_lazy('Lazy single')", "Lazy single"),
        ('pgettext("context", "Double after a context")', "Double after a context"),
        ("pgettext('context', 'Single after a context')", "Single after a context"),
        # Literales adyacentes: Python los une antes de que gettext los vea, y
        # un mensaje largo casi siempre viene partido en varias líneas.
        ('_("first half " "second half")', "first half second half"),
        ("_('first half ' 'second half')", "first half second half"),
        # Comillas escapadas dentro del literal, cada una en su propia forma.
        (r'_("she said \"hi\"")', 'she said "hi"'),
        (r"_('it\'s here')", "it's here"),
        # El caso que motivó el patrón propio de `pgettext`: el contexto NO es
        # una cadena traducible, y leerlo lo reportaría como msgid ausente.
        ("{% translate 'X' context 'eyebrow' %}", "X"),
    ],
)
def test_both_quote_styles_are_scanned(source, expected):
    """El guardián del guardián.

    Todo `_SOURCE_PATTERNS` estaba construido sobre el literal del `.po`, que
    sólo acepta comillas dobles, así que `{% translate 'Texto' %}` era invisible
    para el archivo entero: podía faltar del catálogo, salir en inglés dentro de
    una interfaz en español, y no fallar nada. Había 72 formas así en las
    plantillas el día que se encontró.

    Se afirma sobre `_marked_literals`, que es **el mismo** escaneo que usa
    `_source_strings` -- una copia de ese bucle acá podría quedar bien mientras
    el original se desviaba, que es justo la forma del defecto que este test
    existe para impedir.
    """
    found = [literal for _offset, literal in _marked_literals(source)]

    assert expected in found, f"{source!r} no fue escaneado"


def test_every_single_quoted_translate_in_the_tree_is_scanned():
    """La otra mitad: que lo que hay **de verdad** en el árbol esté cubierto.

    La expectativa se deriva del árbol y no de una lista escrita a mano, así que
    no se queda vieja cuando alguien agrega una forma con comillas simples. El
    `assert expected` de arriba es lo que evita que el test pase en verde el día
    que un refactor deje cero: sin él, "todo lo esperado está cubierto" sería
    cierto sobre un conjunto vacío.
    """
    root = Path(settings.BASE_DIR)
    single_quoted = re.compile(r"\{%\s*(?:translate|trans)\s+'((?:[^'\\]|\\.)*)'")
    expected = set()
    for path in (root / "templates").rglob("*.html"):
        expected.update(
            _unescape(literal)
            for literal in single_quoted.findall(
                path.read_text(encoding="utf-8", errors="replace")
            )
        )

    assert expected, "no hay formas con comillas simples: este test ya no vigila nada"
    assert expected <= set(_source_strings())


def test_the_catalog_side_still_only_accepts_double_quotes():
    """El lado del `.po` **no** se ensanchó, y eso es deliberado: gettext quota
    con `"` y nada más, así que aceptar `'...'` acá haría que el parser del
    catálogo tragara un archivo que gettext rechaza."""
    assert "'" not in _LITERAL
    assert "'" not in _LITERAL_NC
    assert re.fullmatch(_LITERAL_NC, '"texto"')
    assert not re.fullmatch(_LITERAL_NC, "'texto'")


def test_catalog_has_no_duplicate_msgids(catalog):
    """msgmerge refuses to run on a catalog with duplicates, so nobody can
    resync it until they are gone.

    Keyed on (msgctxt, msgid), which is what gettext itself considers unique:
    the same literal under two different contexts is a legitimate pair, not a
    duplicate (LV-61 needed one, "Registry" meaning both the import page's
    eyebrow and the sidebar group over the roster).
    """
    seen, duplicated = set(), []
    for msgctxt, msgid, _msgstr, _fuzzy in catalog:
        key = (msgctxt, msgid)
        if key in seen:
            duplicated.append(f"{msgid!r} (context {msgctxt!r})" if msgctxt else msgid)
        seen.add(key)

    assert not duplicated, f"msgid duplicados en django.po: {sorted(set(duplicated))}"


def test_every_entry_is_translated_and_not_fuzzy(catalog):
    """A fuzzy entry is as invisible as an empty one: gettext skips it and the
    string renders in English."""
    empty = [msgid for _, msgid, msgstr, _ in catalog if not msgstr]
    fuzzy = [msgid for _, msgid, _, is_fuzzy in catalog if is_fuzzy]

    assert not empty, f"sin traducir: {empty}"
    assert not fuzzy, f"marcadas fuzzy, Django las ignora: {fuzzy}"


def test_a_string_inside_a_template_comment_is_not_demanded():
    """LV-169, guardián del guardián: es lo que `makemessages` hace, no un permiso.

    Y el número de línea de lo que viene después **no se corre**, que es lo que
    haría inútil el mensaje de error de este archivo.
    """
    content = (
        '{% translate "Visible" %}\n'
        "{% comment %}\n"
        '{% translate "Retirada del menu" %}\n'
        "{% endcomment %}\n"
        '{% translate "Despues del bloque" %}\n'
    )

    blanked = _without_template_comments(content)
    found = dict(
        (literal, blanked.count("\n", 0, offset) + 1)
        for offset, literal in _marked_literals(blanked)
    )

    assert "Retirada del menu" not in found
    assert found["Visible"] == 1
    assert found["Despues del bloque"] == 5


def test_every_translatable_string_is_in_the_catalog(catalog):
    """Catches the case that started this: `_("Document types")` while the
    catalog held "Document Types". gettext keys are exact, so the lookup missed
    and the English source was displayed."""
    msgids = {msgid for _, msgid, _, _ in catalog}
    lower = {msgid.lower(): msgid for msgid in msgids}

    missing, case_only = [], []
    for literal, where in _source_strings().items():
        if literal in msgids:
            continue
        near = lower.get(literal.lower())
        if near:
            case_only.append(f"{where}: {literal!r} vs {near!r} en el catalogo")
        else:
            missing.append(f"{where}: {literal!r}")

    assert not case_only, "difieren solo en mayusculas:\n  " + "\n  ".join(case_only)
    assert not missing, "ausentes del catalogo:\n  " + "\n  ".join(missing)


def _all_model_forms():
    """Every concrete ModelForm defined under apps/*/forms.py."""
    import importlib
    import pkgutil

    from django import forms as django_forms

    import apps as apps_pkg

    found = {}
    for mod in pkgutil.walk_packages(apps_pkg.__path__, "apps."):
        if not mod.name.endswith(".forms"):
            continue
        module = importlib.import_module(mod.name)
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, django_forms.ModelForm)
                and obj.__module__ == module.__name__
                and getattr(getattr(obj, "Meta", None), "model", None) is not None
            ):
                found[f"{mod.name}.{name}"] = obj
    return found


@pytest.mark.django_db
def test_every_form_label_is_in_the_catalog(catalog):
    """A field with no Meta.labels entry (and no model verbose_name) renders
    Django's auto-derived English label, whose msgid is never in the catalog --
    so it shows in English inside the Spanish UI. The sibling test above only
    sees literals written in the source; an auto-derived label exists nowhere
    in the code, which is exactly why this class of drift stayed invisible.
    This instantiates every form and checks each rendered label/help text
    resolves to a catalog entry.

    This is LV-22 generalized: that fix added explicit labels to one form at a
    time, as each was spotted by eye, which is how 18 of them survived.
    """
    from django.utils.translation import override

    translated = {msgid for _, msgid, msgstr, fuzzy in catalog if msgstr and not fuzzy}
    problems = []
    with override("en"):
        for form_label, form_cls in sorted(_all_model_forms().items()):
            try:
                form = form_cls()
            except Exception:  # noqa: BLE001 - a form needing args isn't reachable bare
                continue
            for name, field in form.fields.items():
                for kind, value in (("label", field.label), ("help", field.help_text)):
                    text = str(value) if value else ""
                    if text and text not in translated:
                        problems.append(f"{form_label}.{name} [{kind}]: {text!r}")

    assert not problems, "labels/help texts sin traducir:\n  " + "\n  ".join(problems)


def test_source_strings_are_written_in_english():
    """The project keeps source strings in English and Spanish in the catalog.
    Two validation messages had been written directly in Spanish, which put the
    translation out of reach of the catalog."""
    accents = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
    offenders = [
        f"{where}: {literal!r}"
        for literal, where in _source_strings().items()
        if accents.search(literal)
    ]

    assert not offenders, "cadenas fuente en espanol:\n  " + "\n  ".join(offenders)


# Formas del voseo rioplatense. La lista es de **verbos conjugados**, no de un
# patrón sobre la tilde: `-ás/-és/-ís` acentuados aparecen en un montón de
# palabras legítimas (`además`, `después`, `país`, `interés`), así que un patrón
# genérico daría falsos positivos en cada revisión y terminaría desactivado.
#
# Dos grupos: el presente (`necesitás`, `podés`) y el imperativo (`usá`, `elegí`,
# `revisá`), que es el que más se cuela porque en un mensaje de ayuda suena
# natural escribir "usá --force".
_VOSEO = [
    # Presente de indicativo.
    # `ves`, `estás` y `sos` **no van**: los dos primeros son tuteo normal y el
    # tercero choca con "SOS" al comparar en minúsculas. Un guardián que marca
    # español correcto es un guardián que alguien termina desactivando.
    "necesitás",
    "podés",
    "tenés",
    "querés",
    "debés",
    "hacés",
    "sabés",
    "elegís",
    "vivís",
    "escribís",
    "seguís",
    "venís",
    "andás",
    "creés",
    "ponés",
    "salís",
    "decís",
    "pedís",
    # Imperativo.
    "usá",
    "elegí",
    "escribí",
    "revisá",
    "mirá",
    "andá",
    "poné",
    "dejá",
    "fijate",
    "acordate",
    "tené",
    "entrá",
    "cargá",
    "subí",
    "volvé",
    "marcá",
    "guardá",
    "apretá",
    "seleccioná",
    "ingresá",
    "probá",
    "esperá",
    "avisá",
    "cerrá",
    "abrí",
    "buscá",
    "agregá",
    "quitá",
    "corregí",
    "completá",
]


def test_the_spanish_catalog_has_no_voseo(catalog):
    """El español del producto es **neutral**, nunca rioplatense.

    Instrucción del usuario, textual: *"ojo el español o la información está con
    un tono argentino, debe ser neutral siempre"*. La app la usa una empresa
    chilena y su interlocutor es la DGAC: un "necesitás" en una pantalla que
    después se imprime como evidencia ISO suena a que el sistema lo escribió
    alguien de afuera.

    **Este guardián existe porque revisarlo a ojo ya falló.** El 2026-09-02 se
    neutralizaron ocho cadenas y se dio el trabajo por cerrado; al día siguiente
    apareció una novena viva en el catálogo, en el mensaje de bloqueo del
    acceso. Una revisión manual que se declara completa y no lo está es peor que
    no haberla hecho, porque nadie vuelve a mirar.
    """
    offenders = []
    for _, msgid, msgstr, fuzzy in catalog:
        if not msgstr or fuzzy:
            continue
        lowered = msgstr.lower()
        for form in _VOSEO:
            # Con límites de palabra para que `usá` no marque `usuario` ni
            # `causá`, y `tené` no marque `tenés` dos veces.
            if re.search(rf"\b{re.escape(form)}\b", lowered):
                offenders.append(f"{form!r} en {msgid[:60]!r}: {msgstr[:80]!r}")
                break

    assert not offenders, "voseo en el catalogo espanol:\n  " + "\n  ".join(offenders)
