"""LV-94/LV-95: the upload form loads its record list, and its type picker groups.

LV-94 is a **found-in-production dead end**, not a cosmetic issue: the entity-type
`<select>` asks HTMX to write the record list into `#document-object-field`, and
that `id` only existed in the modal fragment. On the standalone pages the target
was absent, htmx logged `targetError` and the "Related record" picker stayed
empty forever -- so a document could not be uploaded from there at all. The tests
below assert the two halves *in the same rendered page*, because either one alone
is green while the feature is broken.

LV-95 groups the type catalog. The interesting cases are the ones where grouping
could silently lose an option (an unknown category, an archived type that a
document already carries), since a picker that drops an option looks exactly like
a deleted document type.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.core.testing import login_as
from apps.compliance.forms import DocumentForm, selectable_document_types
from apps.compliance.management.commands.seed_document_types import DOCUMENT_TYPES
from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft

# The HTMX contract this whole file is about: the attribute and the id have to
# name the same thing, and both have to be on the page.
HX_TARGET = 'hx-target="#document-object-field"'
TARGET_ID = 'id="document-object-field"'


@pytest.fixture
def doc_type(db):
    return DocumentType.objects.create(
        name="Póliza",
        code="policy",
        requires_expiry=False,
        category=DocumentType.CATEGORY_AIRCRAFT,
    )


@pytest.mark.django_db
class TestRecordPickerCanBeFilled:
    """LV-94: every page that renders the upload form can reach its record list."""

    def test_the_create_page_carries_the_target_htmx_writes_into(self):
        html = login_as("add_document").get(reverse("document-create")).content.decode()

        assert HX_TARGET in html
        assert TARGET_ID in html

    def test_the_batch_page_carries_it_too(self):
        html = (
            login_as("add_document")
            .get(reverse("document-bulk-upload"))
            .content.decode()
        )

        assert HX_TARGET in html
        assert TARGET_ID in html

    def test_the_replace_page_no_longer_needs_it(self, doc_type):
        """Premise changed by LV-100, not intention.

        This asserted that the replace page carried the target too -- correct
        while that page still offered the record as a picker. It does not any
        more: replacing never moves a document between records, so the record is
        shown as a fact and there is nothing for HTMX to fill. The pairing still
        holds, in the only form that can be true here: **neither** half is
        present, so the page cannot end up with a picker and no target again.
        Its own guarantees live in test_lv99_lv100_upload_screens.py.
        """
        aircraft = Aircraft.objects.create(
            registration="CC-LV94", type="RPA", model="M3", manufacturer="DJI"
        )
        document = Document.objects.create(
            title="Póliza",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date="2026-08-14",
            file_path="policy/aircraft/x/policy.pdf",
        )

        html = (
            login_as("change_document")
            .get(reverse("document-replace", args=[document.pk]))
            .content.decode()
        )

        assert HX_TARGET not in html
        assert TARGET_ID not in html

    def test_the_fragment_the_endpoint_returns_is_that_target(self):
        """The two ends of the swap, checked against each other rather than
        against a literal written twice."""
        content_type = ContentType.objects.get_for_model(Aircraft)

        response = login_as("add_document").get(
            reverse("document-entity-options"), {"entity_type": content_type.pk}
        )

        assert TARGET_ID in response.content.decode()


@pytest.mark.django_db
class TestTypePickerIsGrouped:
    """LV-95: the type list arrives as `<optgroup>`s, and nothing falls out."""

    def _groups(self, form=None):
        """{category value: [option labels]} as the widget will render it.

        Keyed by the category **value**, not by the group heading: the heading
        is translated, so asserting on its text would make these tests pass or
        fail depending on the active language.
        """
        form = form or DocumentForm()
        value_of = {str(label): value for value, label in DocumentType.CATEGORY_CHOICES}
        groups = {}
        for label, options in list(form.fields["doc_type"].choices)[1:]:
            groups[value_of[str(label)]] = [str(text) for _value, text in options]
        return groups

    def test_types_are_grouped_by_category_in_declared_order(self):
        DocumentType.objects.create(
            name="Credencial", code="cred", category=DocumentType.CATEGORY_PERSONNEL
        )
        DocumentType.objects.create(
            name="Matrícula", code="reg", category=DocumentType.CATEGORY_AIRCRAFT
        )

        groups = self._groups()

        assert list(groups) == [
            DocumentType.CATEGORY_PERSONNEL,
            DocumentType.CATEGORY_AIRCRAFT,
        ]
        assert groups[DocumentType.CATEGORY_PERSONNEL] == ["Credencial"]
        assert groups[DocumentType.CATEGORY_AIRCRAFT] == ["Matrícula"]

    def test_the_empty_option_stays_first(self):
        DocumentType.objects.create(name="X", code="x")

        first = list(DocumentForm().fields["doc_type"].choices)[0]

        assert first[0] == ""

    def test_a_type_with_an_unknown_category_is_shown_under_other(self):
        """Not dropped: an option that vanishes reads as a deleted type, and the
        row would be unselectable with nothing on screen saying why."""
        DocumentType.objects.create(name="Rara", code="odd", category="ghost-category")

        assert self._groups()[DocumentType.CATEGORY_OTHER] == ["Rara"]

    def test_every_active_type_appears_exactly_once(self):
        for index, (value, _label) in enumerate(DocumentType.CATEGORY_CHOICES):
            DocumentType.objects.create(
                name=f"T{index}", code=f"t{index}", category=value
            )

        listed = [name for options in self._groups().values() for name in options]

        assert sorted(listed) == sorted(
            DocumentType.objects.values_list("name", flat=True)
        )


@pytest.mark.django_db
class TestWhichTypesAreOffered:
    def test_an_archived_type_is_not_offered(self):
        DocumentType.objects.create(name="Vieja", code="old", is_active=False)

        assert list(selectable_document_types()) == []

    def test_but_the_one_a_document_already_carries_survives(self):
        """Otherwise archiving a type turns "replace this document" into a
        validation error on a field nobody touched."""
        archived = DocumentType.objects.create(
            name="Vieja", code="old", is_active=False
        )

        assert list(selectable_document_types(current_pk=archived.pk)) == [archived]

    def test_a_junk_id_in_the_url_is_ignored_rather_than_crashing(self):
        """`doc_type` is prefilled from a GET parameter, so it is untrusted."""
        DocumentType.objects.create(name="Buena", code="good")

        assert selectable_document_types(current_pk="not-a-uuid").count() == 1


@pytest.mark.django_db
class TestCatalogIsClassified:
    def test_the_seeded_catalog_leaves_nothing_under_other(self):
        from django.core.management import call_command

        call_command("seed_document_types")

        assert not DocumentType.objects.filter(
            category=DocumentType.CATEGORY_OTHER
        ).exists()

    def test_the_backfill_and_the_seed_agree(self):
        """One-directional on purpose.

        Every code the migration classifies must match the catalog, so an
        existing installation and a fresh one end up the same. The reverse is
        **not** asserted: a type added after this migration shipped gets its own
        migration, and demanding it appear in an already-applied one would be
        asking to edit history.
        """
        from importlib import import_module

        # A module name that starts with a digit cannot be written as an
        # `import` statement, which is why this one goes through importlib.
        backfill = import_module(
            "apps.compliance.migrations.0019_lv95_document_type_category"
        )
        seeded = {code: category for code, _n, _e, _i, _o, category in DOCUMENT_TYPES}

        for code, category in backfill.CATEGORY_BY_CODE.items():
            assert seeded[code] == category
