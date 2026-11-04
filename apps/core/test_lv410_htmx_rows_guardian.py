"""LV-410: una lista con plantilla propia no puede responder por htmx con las filas genéricas.

`SearchMixin.htmx_template_name` es `generic/_table_body.html`. Una vista que dibuja filas propias
y no declara el suyo responde la página 1 bien (plantilla completa) y la página 2, la búsqueda en
vivo y el orden con las filas genéricas: otras columnas, desalineadas con los encabezados.
"""

from django.template import engines
from django.urls import get_resolver

from apps.core.views import SearchMixin

GENERIC_ROWS = "generic/_table_body.html"
GENERIC_LIST = "generic/list.html"


def _search_mixin_views():
    found = {}

    def walk(patterns):
        for entry in patterns:
            if hasattr(entry, "url_patterns"):
                walk(entry.url_patterns)
                continue
            view_class = getattr(entry.callback, "view_class", None)
            if view_class and issubclass(view_class, SearchMixin):
                found[view_class] = entry.name

    walk(get_resolver().url_patterns)
    return found


def _extends_generic_list(template_name):
    source = engines["django"].get_template(template_name).template.source
    return f'extends "{GENERIC_LIST}"' in source


def test_guardian_sees_the_search_mixin_lists():
    assert len(_search_mixin_views()) > 20


def test_lists_with_own_template_declare_their_own_htmx_rows():
    broken = [
        f"{cls.__module__}.{cls.__name__} ({cls.template_name})"
        for cls in _search_mixin_views()
        if cls.template_name
        and cls.template_name != GENERIC_LIST
        and not _extends_generic_list(cls.template_name)
        and cls.htmx_template_name == GENERIC_ROWS
    ]
    assert broken == []
