"""LV-115: leer el respaldo, no sólo escribirlo.

`backup` copia la base y deja un manifiesto con tamaño y `sha256`;
`restore_backup` comprueba ese checksum **antes de restaurar**. Las dos piezas
están bien y entre las dos queda un hueco: **nadie mira el respaldo hasta el día
que lo necesita**. El panel de situación muestra el manifiesto del último, que
es lo que se escribió, no lo que hoy hay en el disco.

Y hay una razón técnica para no conformarse con el checksum. Un `sha256` prueba
que **el archivo no cambió desde que se escribió**; no prueba que sea una base
usable. Antes `backup` copiaba el `.sqlite3` con `shutil.copy2` (LV-116 lo
cambió por la API de respaldo en línea de SQLite, igual que `restore_backup`
desde LV-400): ése es el caso que SQLite documenta como riesgoso, porque la
copia puede capturar un estado a medias. El checksum de un archivo roto
coincide perfectamente consigo mismo.

Por eso la verificación **abre** el respaldo y le corre `PRAGMA integrity_check`
más una consulta real. Es la diferencia entre "los bytes están intactos" y "esto
se puede restaurar", que es la única pregunta que importa.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from django.utils.translation import gettext_lazy as _


# LV-401: respaldos de documentos (tar.gz) y retención por cantidad.
DOCS_PREFIX = "aero_docs_"
DOCS_SUFFIX = ".tar.gz"
DOCS_PATTERN = f"{DOCS_PREFIX}*{DOCS_SUFFIX}"
DB_PATTERN = "aero_ops_*.sqlite3"


def docs_manifest_path(archive):
    """`aero_docs_X.tar.gz` -> `aero_docs_X.json` (`with_suffix` dejaría `.tar.json`)."""
    archive = Path(archive)
    return archive.with_name(archive.name[: -len(DOCS_SUFFIX)] + ".json")


def _manifest_for(path):
    path = Path(path)
    if path.name.endswith(DOCS_SUFFIX):
        return docs_manifest_path(path)
    return path.with_suffix(".json")


def _has_valid_manifest(path):
    try:
        manifest = json.loads(_manifest_for(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(manifest, dict)
        and manifest.get("backup") == path.name
        and "sha256" in manifest
    )


def apply_retention(directory, pattern, keep):
    """Borra los respaldos más viejos de `pattern` dejando los `keep` últimos.

    Por **cantidad**, no por antigüedad: si el timer deja de correr, la
    retención por días iría vaciando la carpeta hasta no dejar nada; por
    cantidad, los últimos N quedan siempre. Reglas: nunca el más reciente
    (`keep` mínimo 1), sólo archivos con el patrón propio, y un respaldo sin
    manifiesto válido no se toca (no se sabe qué es). Devuelve los borrados.
    """
    keep = max(1, int(keep))
    # El nombre lleva la fecha, así que ordenar por nombre es ordenar por tiempo
    # sin depender de mtime (que un `scp` o un restore alteran).
    found = sorted(Path(directory).glob(pattern), key=lambda p: p.name, reverse=True)
    removed = []
    for path in found[keep:]:
        if not _has_valid_manifest(path):
            continue
        manifest = _manifest_for(path)
        path.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def latest_backup():
    """{name, path, manifest} del respaldo más reciente con manifiesto válido.

    Extraído de `AdministrationCenterView._latest_backup` cuando apareció el
    segundo lector -- la verificación programada --, que es cuando este repo
    extrae. Recorre por fecha de archivo y se queda con el primero que tenga un
    manifiesto legible: un `.json` a medio escribir de una corrida interrumpida
    no debe tapar al respaldo bueno de ayer.
    """
    from apps.core.management.commands.backup import backups_dir

    directory = backups_dir()
    try:
        manifests = sorted(
            directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        return None
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "sha256" not in manifest or manifest.get("kind") == "documents":
            # LV-401: el respaldo de documentos no es una base; `verify` lo
            # abriría con SQLite y lo daría por corrupto.
            continue
        return {
            "name": manifest.get("backup", manifest_path.stem),
            "path": directory / manifest.get("backup", ""),
            "manifest": manifest,
        }
    return None


def load_manifest(path):
    """El respaldo de esta ruta con su manifiesto, o None si falta alguno.

    Lo que el modo manual necesita para verificar **un archivo concreto** con la
    misma maquinaria que el chequeo diario. Dos implementaciones de "verificar"
    serían la peor forma de este defecto: que el automático diga "sano" con una
    regla más floja que la del que corre a mano antes de restaurar.
    """
    manifest_path = path.with_suffix(".json")
    if not path.is_file() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("backup") != path.name:
        return None
    return {"name": path.name, "path": path, "manifest": manifest}


def _problem(code, message):
    """Un problema lleva **código y mensaje**.

    El mensaje se traduce, así que identificar un problema por su texto hace que
    el código que lo lee dependa del idioma activo -- la trampa que este
    proyecto ya pagó en `LV-95`, `LV-107` y de nuevo acá. El código es para
    quien decide; el mensaje, para quien lee el correo.
    """
    return {"code": code, "message": message}


def verify(backup):
    """Los problemas del respaldo, en una lista. Vacía significa restaurable.

    Devuelve problemas en vez de lanzar o devolver un booleano: "está mal" no
    dice qué hacer, y las causas se arreglan distinto -- falta el archivo (el
    trabajo no corrió o alguien lo movió), no coincide el checksum (se corrompió
    en disco), o abre pero la base está rota (se copió a medias).
    """
    problems = []
    path = Path(backup["path"])
    manifest = backup["manifest"]
    if not path.is_file():
        return [
            _problem(
                "missing_file",
                _("The backup file named in the manifest is not there"),
            )
        ]

    if path.stat().st_size != manifest.get("size"):
        problems.append(_problem("size", _("The size does not match the manifest")))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != manifest.get("sha256"):
        problems.append(
            _problem("checksum", _("The checksum does not match the manifest"))
        )

    # Abrir en sólo lectura: verificar un respaldo no puede ser una forma de
    # modificarlo. `immutable=1` además evita que SQLite intente crear archivos
    # auxiliares (-wal, -shm) junto al respaldo.
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        problems.append(
            _problem("unopenable", _("The backup cannot be opened as a database"))
        )
        return problems
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            problems.append(
                _problem("corrupt", _("The database inside the backup is corrupt"))
            )
        else:
            # Una consulta de verdad: `integrity_check` valida la estructura del
            # archivo, no que contenga la aplicación. Un archivo SQLite vacío y
            # perfectamente sano pasaría lo anterior y no serviría para nada.
            tables = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            if tables < 2:
                problems.append(
                    _problem(
                        "empty",
                        _("The backup opens but holds no application tables"),
                    )
                )
    except sqlite3.DatabaseError:
        problems.append(
            _problem("corrupt", _("The database inside the backup is corrupt"))
        )
    finally:
        connection.close()
    return problems
