"""LV-80: the create/list screen titles rendered in English inside a Spanish UI.

The cause was subtler than "no translation": most of these models **do** declare
a translated `verbose_name`. What broke it was `.title()` -- calling it evaluates
the lazy proxy into an English string, and the surrounding `_()` then looks *that*
up ("New Document"), which is in no catalog. So the fix is not to translate
harder, it is to stop re-translating: use the model's own verbose_name and
capitalize the already-translated result.

Two guards, because either alone lets the defect back in: one that the pattern
does not reappear, and one that the names it now relies on are actually
translated.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.utils.text import capfirst
from django.utils.translation import gettext, override

REPO_ROOT = Path(__file__).resolve().parents[2]

# The apps whose list/create/update views build a title from the model's name.
TITLE_BUILDING_APPS = [
    "compliance",
    "geo",
    "maintenance",
    "operations",
    "registry",
    "workboard",
]

# `_(anything-that-is-not-a-string-literal)`: makemessages cannot see it, so the
# msgid never reaches the catalog and the lookup falls through to English at run
# time. AGENTS.md forbids it; this is the case that got past review because the
# variable *looked* like it was already translated.
#
# The lookbehind matters: without it `def __str__(self):` matches, because that
# line does end in `_(self`.
UNEXTRACTABLE = re.compile(r"(?<![\w])_\(\s*(?!['\"])[A-Za-z_][\w.]*[\w.()\[\]]*\s*\)")


def _source_files():
    for app in TITLE_BUILDING_APPS:
        yield from (REPO_ROOT / "apps" / app).rglob("*.py")


class TestThePatternDoesNotComeBack:
    def test_no_view_translates_a_variable(self):
        """It is comfortable to write, which is exactly why it needs a test and
        not a note: `_(model._meta.verbose_name.title())` reads as careful i18n
        and produces English."""
        offenders = []
        for path in _source_files():
            if "migrations" in path.parts or path.name.startswith("test_"):
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if UNEXTRACTABLE.search(line):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{number} {stripped}"
                    )

        assert offenders == [], "translate literals, never variables:\n" + "\n".join(
            offenders
        )


@pytest.mark.django_db
class TestTheNamesAreTranslated:
    """The titles now read the model's own verbose_name, so those have to be
    translated -- otherwise the screen is still English, just by a different
    route."""

    MODELS = [
        ("compliance", "Document"),
        ("compliance", "DocumentType"),
        ("compliance", "Alert"),
        ("compliance", "AlertRule"),
        ("operations", "FlightPermission"),
        ("operations", "FlightRecord"),
        ("registry", "Aircraft"),
        ("registry", "Operator"),
        ("registry", "CostCenter"),
        ("registry", "Qualification"),
        ("maintenance", "MaintenanceRecord"),
    ]

    @pytest.mark.parametrize(("app_label", "model_name"), MODELS)
    def test_the_singular_and_plural_have_a_spanish_reading(
        self, app_label, model_name
    ):
        model = django_apps.get_model(app_label, model_name)

        with override("es"):
            singular = str(model._meta.verbose_name)
            plural = str(model._meta.verbose_name_plural)

        with override("en"):
            english_singular = str(model._meta.verbose_name)
            english_plural = str(model._meta.verbose_name_plural)

        assert (singular, plural) != (english_singular, english_plural), (
            f"{app_label}.{model_name} has no translated verbose_name, so its "
            "screen title renders in English"
        )

    def test_no_template_hardcodes_an_english_browser_tab_title(self):
        """The tab title is visible text too. Four templates spelled it out in
        English ("New Document - AeroControl") while the page heading beneath it
        was already Spanish -- the generic templates had it right all along,
        deriving it from the same `title` the view provides."""
        pattern = re.compile(
            r"{%\s*block title\s*%}\s*[A-Z][A-Za-z ]+\s*-\s*AeroControl"
        )
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in (REPO_ROOT / "templates").rglob("*.html")
            if pattern.search(path.read_text(encoding="utf-8"))
        ]

        assert offenders == [], (
            "derive the tab title from the view's `title`, or translate it:\n"
            + "\n".join(offenders)
        )

    def test_a_title_reads_as_spanish_end_to_end(self):
        model = django_apps.get_model("compliance", "Document")

        with override("es"):
            title = gettext("New %(record)s") % {"record": model._meta.verbose_name}
            plural_title = capfirst(model._meta.verbose_name_plural)

        assert "New " not in title
        assert plural_title[0].isupper()
