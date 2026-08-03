"""Shared context for a detail page's "Documents" section.

Aircraft, operator, cost-center (and the flight-permission page that pioneered
the pattern) all attach compliance Documents through the same generic pipeline.
This builds the context they need -- the record's current documents plus its
ContentType id for the prefilled upload link -- gated by compliance.view_document,
so the section stays one implementation instead of four.
"""

from django.contrib.contenttypes.models import ContentType

from .models import Document


def attached_documents_context(user, obj):
    """Return {'documents', 'document_content_type_id'} for `obj`'s detail page.

    `documents` is None (the section hides itself) when the user cannot view
    documents; otherwise it is the object's current, active documents.
    """
    if not user.has_perm("compliance.view_document"):
        return {"documents": None, "document_content_type_id": None}
    content_type = ContentType.objects.get_for_model(obj)
    documents = (
        Document.objects.filter(
            content_type=content_type,
            object_id=obj.pk,
            is_current_version=True,
            is_active=True,
        )
        .select_related("doc_type")
        .order_by("-issue_date")
    )
    return {"documents": documents, "document_content_type_id": content_type.pk}
