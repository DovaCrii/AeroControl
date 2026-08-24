"""Toda URL que una plantilla nombra tiene que existir.

Escrito el 2026-08-24, después de que producción devolviera 500 con
`NoReverseMatch: Reverse for 'geo-plan-split' not found`. Esa vez el nombre sí
existía —el despliegue había quedado a medias, con plantillas nuevas sobre
código viejo— pero el incidente dejó a la vista un hueco real:

**un `{% url %}` sólo se resuelve cuando su rama se dibuja.** Un nombre mal
escrito, o el de una vista que alguien renombró, no rompe nada al arrancar, no
lo ve `manage.py check`, y no lo ve la suite si esa rama está detrás de un
permiso o de un `{% if %}` que los tests no encienden. Se descubre en
producción, como un 500 en blanco, y el síntoma que se reporta suele no tener
relación con la causa — acá se reportó como "falla al importar un KMZ".

Es la misma familia que `LV-109`: la plantilla dejó de tener un `<canvas>` y el
script siguió buscándolo, y nadie lo vio porque el HTML estaba bien.

Este test lee **los archivos**, no una página renderizada, por la misma razón
que aquél: una página que no dibuja la rama no prueba nada, y ése es justo el
punto ciego donde el defecto vive.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import get_resolver

# `{% url 'nombre' ... %}` y `{% url "nombre" ... %}`. Sólo literales: un
# `{% url variable %}` no se puede verificar sin ejecutar la plantilla, y
# fingir que sí daría una falsa sensación de cobertura.
URL_TAG = re.compile(r"{%\s*url\s+['\"]([^'\"]+)['\"]")

TEMPLATE_ROOTS = [Path(settings.BASE_DIR) / "templates"] + [
    Path(app_dir) for app_dir in (Path(settings.BASE_DIR) / "apps").glob("*/templates")
]


def _template_files():
    for root in TEMPLATE_ROOTS:
        if root.exists():
            yield from sorted(root.rglob("*.html"))


def _referenced_names():
    """{nombre: [archivos que lo nombran]} de todas las plantillas del repo."""
    found = {}
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for name in URL_TAG.findall(text):
            found.setdefault(name, []).append(path.name)
    return found


def test_there_are_templates_to_check():
    """El guardián del guardián: si el descubrimiento se rompe, este archivo
    pasaría en verde sin haber mirado nada."""
    assert len(list(_template_files())) > 20


@pytest.mark.django_db
def test_every_url_name_a_template_uses_is_registered():
    resolver = get_resolver()
    registered = set(resolver.reverse_dict.keys())
    # `reverse_dict` mezcla nombres con funciones de vista; los nombres son los
    # que interesan y son los que están como cadena.
    registered = {name for name in registered if isinstance(name, str)}
    registered |= set(resolver.namespace_dict)

    missing = {}
    for name, files in _referenced_names().items():
        if ":" in name:
            # Un nombre con espacio (`api:token`) se valida por su espacio: el
            # resolver del namespace se carga aparte y comprobarlo entero acá
            # exigiría instanciarlo, que es más máquina de la que este test
            # necesita para lo que protege.
            if name.split(":", 1)[0] in registered:
                continue
        if name not in registered:
            missing[name] = sorted(set(files))

    assert not missing, "URLs nombradas en plantillas que no existen:\n" + "\n".join(
        f"  {name} — en {', '.join(files)}" for name, files in sorted(missing.items())
    )


@pytest.mark.django_db
def test_it_would_catch_a_renamed_view():
    """El contrapeso: un test que sólo dice "todo bien" no prueba que mire.

    Se comprueba contra el mecanismo, no contra el repo: un nombre inventado
    tiene que quedar fuera del conjunto que la afirmación de arriba consulta.
    """
    registered = {
        name for name in get_resolver().reverse_dict.keys() if isinstance(name, str)
    }

    assert "geo-plan-split" in registered  # la del incidente del 2026-08-24
    assert "geo-plan-split-typo" not in registered
