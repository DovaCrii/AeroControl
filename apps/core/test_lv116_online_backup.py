"""LV-116: el respaldo se toma con la API de SQLite, no copiando bytes.

Era `shutil.copy2`, que no sabe nada de SQLite: si alguien guarda algo mientras
la copia avanza, el archivo puede quedar a medio camino entre dos estados.

**No es teórico acá.** Mirando `p340` el 2026-08-17 apareció que el respaldo "de
las 22:00" corre a las **18:00 hora de Chile** —el sistema operativo está en UTC
y Django sella los nombres en hora local—, o sea en plena jornada y con la
aplicación en uso. El respaldo de esa noche verificó bien, pero por suerte
estructural, no por diseño.

`Connection.backup()` toma un punto consistente aunque haya escritores. El test
que lo demuestra es el que mantiene una **transacción abierta a medias** durante
la copia: con `copy2` el respaldo podía incluirla; acá no aparece, que es la
definición de consistente.
"""

import sqlite3

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.core.backups import latest_backup, verify


@pytest.fixture
def source(tmp_path, monkeypatch):
    """Una base con datos, puesta como la base de la aplicación."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path / "backups"))
    path = tmp_path / "source.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE registry_aircraft (id INTEGER PRIMARY KEY)")
    connection.execute("CREATE TABLE compliance_document (id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO registry_aircraft (id) VALUES (1)")
    connection.commit()
    connection.close()
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", str(path))
    monkeypatch.setattr(
        "apps.core.management.commands.backup.backups_dir",
        lambda: tmp_path / "backups",
    )
    return path


@pytest.mark.django_db
def test_the_backup_is_a_usable_database(source):
    call_command("backup")

    assert verify(latest_backup()) == []


@pytest.mark.django_db
def test_it_carries_the_data(source):
    call_command("backup")

    backup = latest_backup()
    connection = sqlite3.connect(backup["path"])
    try:
        rows = connection.execute("SELECT count(*) FROM registry_aircraft").fetchone()[
            0
        ]
    finally:
        connection.close()

    assert rows == 1


@pytest.mark.django_db
def test_a_write_in_flight_does_not_land_half_way_into_the_backup(source):
    """El punto de todo el cambio.

    Con una transacción abierta y sin confirmar durante la copia, el respaldo
    tiene que reflejar el estado **anterior**: consistente, no a medias. Copiar
    bytes no puede garantizar esto; la API de respaldo de SQLite sí.
    """
    writer = sqlite3.connect(source)
    writer.execute("BEGIN")
    writer.execute("INSERT INTO registry_aircraft (id) VALUES (2)")

    try:
        call_command("backup")
    finally:
        writer.rollback()
        writer.close()

    backup = latest_backup()
    assert verify(backup) == []
    connection = sqlite3.connect(backup["path"])
    try:
        ids = [row[0] for row in connection.execute("SELECT id FROM registry_aircraft")]
    finally:
        connection.close()
    assert ids == [1]


@pytest.mark.django_db
def test_a_missing_database_fails_instead_of_producing_an_empty_backup(
    tmp_path, monkeypatch
):
    """Defecto introducido al cambiar de `copy2` a la API de SQLite, y peor que
    el original: `sqlite3.connect` **crea** el archivo si no existe, así que una
    base ausente producía un respaldo vacío y un trabajo en verde. Un respaldo
    que no existe es mejor que uno que dice existir y está vacío."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    monkeypatch.setitem(
        settings.DATABASES["default"], "NAME", str(tmp_path / "no-existe.sqlite3")
    )

    with pytest.raises(FileNotFoundError):
        call_command("backup")


@pytest.mark.django_db
def test_the_manifest_still_describes_the_file(source):
    """El manifiesto se calcula sobre el archivo ya escrito, así que cambiar
    cómo se copia no puede desalinearlo -- pero es exactamente el tipo de cosa
    que se rompe sin que nadie mire."""
    call_command("backup")

    backup = latest_backup()
    assert backup["manifest"]["size"] == backup["path"].stat().st_size
