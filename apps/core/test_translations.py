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
_LITERAL = r'"((?:[^"\\]|\\.)*)"'
_LITERAL_NC = r'"(?:[^"\\]|\\.)*"'

# Strings marked for translation in Python and in templates. The Python pattern
# takes one or more adjacent literals, because a long message is usually split
# over several lines and Python joins them before gettext ever sees it.
_SOURCE_PATTERNS = [
    re.compile(
        r"(?:\b_|gettext|gettext_lazy|pgettext)\(\s*((?:" + _LITERAL_NC + r"\s*)+)"
    ),
    re.compile(r"\{%\s*(?:translate|trans)\s+(" + _LITERAL_NC + r")"),
]


def _unescape(value):
    return value.replace('\\"', '"').replace("\\\\", "\\")


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
        for pattern in _SOURCE_PATTERNS:
            for match in pattern.finditer(content):
                literal = _unescape("".join(re.findall(_LITERAL, match.group(1))))
                line = content.count("\n", 0, match.start()) + 1
                found.setdefault(literal, f"{path.relative_to(root).as_posix()}:{line}")
    return found


@pytest.fixture(scope="module")
def catalog():
    return list(_entries())


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
