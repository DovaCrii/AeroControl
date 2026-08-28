"""LV-180: "Geo source" pasa a llamarse como lo que es, también en producción.

Fila capturada durante la revisión en vivo. En una app cuya interfaz es española
y donde los tipos de documento nombran papeles reales —"Autorización de Operación
RPA"—, "Geo source" era el único anglicismo del conjunto, y encima jerga.

**Lo que hace a esta fila distinta de un cambio de etiqueta** es que no alcanza
con cambiar el código: el nombre se fija en los `defaults` de un `get_or_create`,
y los `defaults` **sólo se usan al crear**. Sin migración de datos, la fila que ya
existe en producción se queda con el nombre viejo para siempre mientras el código
dice otra cosa — el peor de los dos mundos, porque nadie sospecha.

Las propiedades que estos tests sostienen:

- **El código no cambia.** `GEO_SOURCE` lo referencian otras partes y no lo ve
  nadie; renombrar la llave por cambiar la etiqueta rompería referencias.
- **La migración renombra la fila existente**, que es la razón de existir.
- **No pisa un nombre que alguien haya puesto a mano.** Filtra por el nombre
  viejo: si ya lo renombraron en el admin, esa elección manda.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.compliance.models import DocumentType
from apps.geo.views import GEO_SOURCE_DOC_TYPE_CODE, GEO_SOURCE_DOC_TYPE_NAME

MIGRATION = ("compliance", "0024_lv180_geo_source_gets_a_readable_name")
OLD_NAME = "Geo source"


def test_the_code_did_not_change():
    """Es la llave, no la etiqueta: otras partes la referencian."""
    assert GEO_SOURCE_DOC_TYPE_CODE == "GEO_SOURCE"


def test_the_name_is_in_spanish_like_every_other_document_type():
    """Es dato, no cadena fuente: viaja a la base y ningún `gettext` lo toca."""
    assert GEO_SOURCE_DOC_TYPE_NAME == "Archivo KMZ/KML de origen"
    assert "Geo source" != GEO_SOURCE_DOC_TYPE_NAME


@pytest.mark.django_db
def test_the_migration_renames_the_row_that_already_exists():
    """La razón de existir de la fila: los `defaults` no alcanzan."""
    legacy = DocumentType.objects.create(code=GEO_SOURCE_DOC_TYPE_CODE, name=OLD_NAME)

    executor = MigrationExecutor(connection)
    migration = executor.loader.get_migration(*MIGRATION)
    apps_state = executor.loader.project_state(MIGRATION).apps
    migration.operations[0].code(apps_state, connection.schema_editor())

    legacy.refresh_from_db()
    assert legacy.name == GEO_SOURCE_DOC_TYPE_NAME


@pytest.mark.django_db
def test_it_does_not_overwrite_a_name_somebody_chose_by_hand():
    """Si ya lo renombraron en el admin, esa elección manda."""
    chosen = DocumentType.objects.create(
        code=GEO_SOURCE_DOC_TYPE_CODE, name="KMZ de la faena"
    )

    executor = MigrationExecutor(connection)
    migration = executor.loader.get_migration(*MIGRATION)
    apps_state = executor.loader.project_state(MIGRATION).apps
    migration.operations[0].code(apps_state, connection.schema_editor())

    chosen.refresh_from_db()
    assert chosen.name == "KMZ de la faena"
