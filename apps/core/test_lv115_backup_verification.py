"""LV-115: comprobar que el respaldo sirve, sin esperar a necesitarlo.

`backup` escribe y `restore_backup` verifica **al restaurar**. Entre las dos
queda el hueco: nadie mira el respaldo hasta el día que hace falta, y el panel de
situación muestra el manifiesto —lo que se escribió— y no lo que hoy hay en el
disco.

El test que da sentido a todo esto es
`test_a_corrupt_database_with_a_matching_checksum_is_caught`: un `sha256` prueba
que el archivo **no cambió desde que se escribió**, no que sea una base usable.
`backup` copia el `.sqlite3` mientras la aplicación puede estar escribiendo —el
caso que SQLite documenta como riesgoso— así que un respaldo roto de nacimiento
tiene un checksum perfectamente válido. Por eso se abre y se consulta.
"""

import hashlib
import json
import sqlite3

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.backups import latest_backup, verify
from apps.core.groups import REPORT_RECIPIENTS
from apps.core.models import JobRun


@pytest.fixture
def backups_dir(tmp_path, monkeypatch):
    directory = tmp_path / "backups"
    directory.mkdir()
    monkeypatch.setattr(
        "apps.core.management.commands.backup.backups_dir", lambda: directory
    )
    return directory


@pytest.fixture
def direccion(db):
    group = Group.objects.create(name=REPORT_RECIPIENTS)
    user = User.objects.create_user("jefa", email="jefa@jej.cl", password="pw")
    user.groups.add(group)
    return group


def _write_backup(directory, name="aero_ops_20260817_090000", *, healthy=True):
    """Un respaldo con su manifiesto, sano o roto, siempre **coherente**: el
    manifiesto describe el archivo tal como quedó."""
    path = directory / f"{name}.sqlite3"
    if healthy:
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE registry_aircraft (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE compliance_document (id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.close()
    else:
        # Cabecera de SQLite y basura detrás: es lo que deja una copia hecha a
        # media escritura, y lo que el checksum no puede distinguir de un
        # respaldo bueno.
        path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "backup": path.name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "created_at": "2026-08-17T09:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.django_db
class TestWhatVerificationCatches:
    def test_a_healthy_backup_has_no_problems(self, backups_dir):
        _write_backup(backups_dir)

        assert verify(latest_backup()) == []

    def test_a_corrupt_database_with_a_matching_checksum_is_caught(self, backups_dir):
        """El test que justifica abrir el archivo en vez de sólo hashearlo."""
        _write_backup(backups_dir, healthy=False)

        problems = verify(latest_backup())

        assert problems != []

    def test_a_file_changed_after_the_manifest_is_caught(self, backups_dir):
        """Por **código**, no por el texto del mensaje: el mensaje se traduce, y
        buscar "checksum" en él hacía pasar este test en aislado y fallar con la
        suite completa, donde otro test deja el español activo. Tercera vez que
        esta trampa muerde hoy (`LV-95`, `LV-107`), y por eso `verify` devuelve
        código además de mensaje."""
        path = _write_backup(backups_dir)
        path.write_bytes(path.read_bytes() + b"basura")

        codes = {problem["code"] for problem in verify(latest_backup())}

        assert "checksum" in codes

    def test_a_missing_file_is_caught(self, backups_dir):
        path = _write_backup(backups_dir)
        backup = latest_backup()
        path.unlink()

        assert verify(backup) != []

    def test_an_empty_but_valid_sqlite_file_does_not_pass_as_a_backup(
        self, backups_dir
    ):
        """`PRAGMA integrity_check` valida la estructura del archivo, no que
        contenga la aplicación: una base vacía y perfectamente sana pasaría."""
        path = backups_dir / "aero_ops_vacio.sqlite3"
        sqlite3.connect(path).close()
        (backups_dir / "aero_ops_vacio.json").write_text(
            json.dumps(
                {
                    "backup": path.name,
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

        assert verify(latest_backup()) != []


@pytest.mark.django_db
class TestWhoFindsOut:
    def test_it_mails_direccion_when_the_backup_does_not_verify(
        self, backups_dir, direccion
    ):
        _write_backup(backups_dir, healthy=False)

        call_command("verify_backup")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["jefa@jej.cl"]

    def test_silence_when_the_backup_is_restorable(self, backups_dir, direccion):
        _write_backup(backups_dir)

        call_command("verify_backup")

        assert mail.outbox == []

    def test_having_no_backup_at_all_is_reported_not_skipped(
        self, backups_dir, direccion
    ):
        """No tener respaldo es peor que tener uno malo: salir en silencio por
        "no hay nada que verificar" sería el peor de los dos mundos."""
        call_command("verify_backup")

        assert len(mail.outbox) == 1

    def test_the_mail_says_what_to_do(self, backups_dir, direccion):
        """Un aviso de respaldo roto sin siguiente paso deja a quien lo lee sin
        saber si perdió algo."""
        _write_backup(backups_dir, healthy=False)

        call_command("verify_backup")

        assert "manage.py backup" in mail.outbox[0].body

    def test_it_records_its_own_run(self, backups_dir, direccion):
        _write_backup(backups_dir)

        call_command("verify_backup")

        run = JobRun.objects.filter(command="verify_backup").first()
        assert run.result == JobRun.RESULT_OK
        assert "restorable" in run.summary


@pytest.mark.django_db
class TestTheManualModeStillBehavesAsItAlwaysDid:
    """`verify_backup <archivo>` existía antes de `LV-115` y lo usa quien está
    por restaurar: tiene que **plantarse**, no mandar un correo. Se conservó al
    agregar el modo programado -- son la misma pregunta con dos audiencias, y
    dos implementaciones de la verificación se habrían desincronizado."""

    def test_a_healthy_backup_passes_quietly(self, backups_dir):
        path = _write_backup(backups_dir)

        call_command("verify_backup", str(path))

        assert mail.outbox == []

    def test_a_tampered_backup_raises_instead_of_mailing(self, backups_dir, direccion):
        path = _write_backup(backups_dir)
        with path.open("ab") as stream:
            stream.write(b"tampered")

        with pytest.raises(CommandError):
            call_command("verify_backup", str(path))

        assert mail.outbox == []

    def test_a_missing_backup_raises(self, backups_dir):
        with pytest.raises(CommandError):
            call_command("verify_backup", str(backups_dir / "no-existe.sqlite3"))


@pytest.mark.django_db
def test_the_admin_panel_reads_the_same_backup_as_the_verification(backups_dir):
    """Extraído a `core.backups` para esto: si el panel mirara un respaldo y la
    verificación otro, el panel podría mostrar en verde el que está roto."""
    from apps.core.views import AdministrationCenterView

    _write_backup(backups_dir)

    assert AdministrationCenterView._latest_backup()["name"] == latest_backup()["name"]
