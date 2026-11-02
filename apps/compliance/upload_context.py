"""LV-387: what a record's page proposes when someone uploads a document for it.

Two small pieces of knowledge, kept out of the views so the upload form, the
detail pages' "Upload..." menu and the dossier shortcuts all say the same thing:

* which document types are the usual ones for each kind of record
  (`SUGGESTED_TYPE_CODES`), and
* how to turn the `doc_type` of a query string -- a stable `code`, or a pk for
  the links that predate it -- into a usable, active type (`resolve_doc_type`).

Nothing here trusts the parameter: an unknown or archived type resolves to
`None` and the caller ignores it.
"""

from uuid import UUID

from django.core.exceptions import ValidationError

from .models import DocumentType

# (app_label, model) -> document-type codes, in the order they are offered.
# Not a column on `DocumentType`: it is an editorial choice about the pages, and
# a migration to change a menu would be the wrong price.
SUGGESTED_TYPE_CODES = {
    ("registry", "aircraft"): [
        "airworthiness-cert",
        "aircraft-registration",
        "liability-insurance",
        "jac-insurance-approval",
        "maintenance-certificate",
        "calibration-certificate",
    ],
    ("registry", "operator"): ["dgac-credential", "medical-cert"],
    ("operations", "flightpermission"): [
        "dgac-flight-permit",
        "dgac-rpa-operation-authorization",
        "flight-request",
        "flight-log-txt",
    ],
    ("maintenance", "maintenancerecord"): [
        "maintenance-certificate",
        "calibration-certificate",
    ],
    ("geo", "geoplan"): ["flight-request", "dgac-flight-permit"],
    ("operations", "flightrequest"): ["flight-request", "dgac-flight-permit"],
}

# The operator's DGAC credential has a flow of its own (it reads the PDF and asks
# for confirmation); the menu points there instead of at the generic form.
OWN_UPLOAD_FLOWS = {("registry", "operator", "dgac-credential"): "#credential-upload"}


def suggested_codes_for(app_label, model):
    return list(SUGGESTED_TYPE_CODES.get((app_label, model), []))


def resolve_doc_type(raw):
    """The active `DocumentType` a query-string value names, or `None`.

    Accepts the type's `code` (what links carry now) or its pk (what they
    carried before, and what bookmarks may still hold).
    """
    raw = (str(raw) if raw is not None else "").strip()
    if not raw:
        return None
    by_code = DocumentType.objects.filter(code=raw, is_active=True).first()
    if by_code is not None:
        return by_code
    try:
        pk = UUID(raw)
    except (AttributeError, TypeError, ValueError, ValidationError):
        return None
    return DocumentType.objects.filter(pk=pk, is_active=True).first()


def suggested_upload_types(content_type, can_use_own_flow=lambda code: False):
    """The menu entries for a record: `{"code", "name", "anchor"}` in map order.

    Codes missing from the catalog (or archived) are left out. `anchor` is the
    fragment of the page's own upload flow for that type, or `""` for the
    generic form.
    """
    codes = suggested_codes_for(content_type.app_label, content_type.model)
    if not codes:
        return []
    types = {
        t.code: t for t in DocumentType.objects.filter(code__in=codes, is_active=True)
    }
    entries = []
    for code in codes:
        document_type = types.get(code)
        if document_type is None:
            continue
        anchor = OWN_UPLOAD_FLOWS.get(
            (content_type.app_label, content_type.model, code)
        )
        entries.append(
            {
                "code": code,
                "name": document_type.name,
                "anchor": anchor if anchor and can_use_own_flow(code) else "",
            }
        )
    return entries
