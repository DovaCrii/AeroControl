"""Shared context for a detail page's "Documents" section.

Aircraft, operator, cost-center (and the flight-permission page that pioneered
the pattern) all attach compliance Documents through the same generic pipeline.
This builds the context they need -- the record's current documents plus its
ContentType id for the prefilled upload link -- gated by compliance.view_document,
so the section stays one implementation instead of four.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Case, IntegerField, Value, When

from .models import Document, DocumentType


def category_rank():
    """Orden de las categorías **como las declara el modelo**, no alfabético.

    LV-104. `order_by("doc_type__category")` ordenaría por el valor guardado
    ("aircraft", "company", "dgac"…), que no significa nada para quien lee: la
    lista saldría en orden alfabético *en inglés* dentro de una interfaz en
    español. Este `Case` reproduce el orden de `CATEGORY_CHOICES`, que es el
    mismo que usa el selector del formulario de carga — así la ficha y el
    formulario cuentan la misma historia.
    """
    return Case(
        *[
            When(doc_type__category=value, then=Value(index))
            for index, (value, _label) in enumerate(DocumentType.CATEGORY_CHOICES)
        ],
        # Una categoría que ya no existe en el modelo va al final, igual que en
        # el selector agrupado: no se pierde, pero tampoco encabeza la lista.
        default=Value(len(DocumentType.CATEGORY_CHOICES)),
        output_field=IntegerField(),
    )


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
        # LV-104: agrupados por categoría, y dentro de cada una el más reciente
        # primero -- que era el orden anterior y sigue siendo el correcto dentro
        # del grupo. Una carpeta de veinte documentos ordenada sólo por fecha
        # obliga a leerla entera para encontrar el seguro; agrupada, se salta
        # directo al bloque.
        .annotate(category_rank=category_rank())
        .order_by("category_rank", "-issue_date")
    )
    return {"documents": documents, "document_content_type_id": content_type.pk}
