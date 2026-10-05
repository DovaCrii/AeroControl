# Convenciones de AeroControl

Resumen operativo de `AGENTS.md` (que manda si hay diferencia). Contenido:
1. Dominio y datos · 2. Contrato de permisos · 3. Traducciones (i18n) · 4. Git y ramas · 5. Calidad y CI

## 1. Dominio y datos

- `apps.core.BaseModel`: PK UUID, `created_at`/`updated_at`, `is_active` (archivado lógico), `notes` opcional.
- **Nunca borrar filas operativas**: se archiva. FKs operativos con `on_delete=PROTECT`; no introducir más `CASCADE` (ver `AUDIT_CLAUDE.md` F-07).
- "Fat models, thin views": la regla de negocio vive en el modelo. Ninguna regla en templates, serializers ni solo en el formulario (el admin, la API o un import la evaden): espejar en `clean()` o `CheckConstraint`.
- Auditoría: toda mutación autenticada relevante queda en `AuditEvent` (append-only) vía `apps.core.audit.set_audit_context` en la vista.
- Rutas de datos (`DB_PATH`, `DOCUMENTS_DIR`, `LOGS_DIR`, `BACKUPS_DIR`) fuera del repo. Nunca commitear datos operativos, documentos, backups ni secretos.
- Cambios de modelo: migración revisada y con nombre descriptivo + pruebas de regresión de la regla que la motiva. Chequeos previos a una migración con `values_list`, nunca `.all()` (corren con código nuevo sobre base vieja).
- Despliegue decidido: web en intranet. PostgreSQL solo cuando haya concurrencia real (`docs/postgresql-readiness.md`); no migrar antes.

## 2. Contrato de permisos (toda vista nueva)

- Vistas mutantes exigen `add_*`/`change_*`/`delete_*`.
- **Toda vista de lectura** (listado, detalle, exportación, API) exige `view_*` explícito. `LoginRequiredMixin` a secas fue el origen de los hallazgos F-05/F-06. Las excepciones existentes (`WorkTrayView`, `CanIFlyView`, `GlobalSearchView`, etc.) están justificadas en su docstring: documentar igual cualquier excepción nueva.
- Si el modelo tiene aislamiento por tenant, acotar el queryset con `scope_queryset_to_tenant`, no solo por permiso.
- **Prueba de 403** para un usuario sin el permiso, y prueba cross-tenant cuando aplique.
- Sin `fields = "__all__"` en formularios de escritura. Sin `|safe` con JSON de usuario: `json_script`.
- Exportaciones CSV/XLSX/DOCX neutralizan fórmulas: reutilizar `CsvExportMixin`.
- Al agregar un campo a `Meta.fields`, revisar si la plantilla dibuja campo por campo (`as_crispy_field`): un campo declarado y no dibujado se guarda vacío en cada POST.

## 3. Traducciones (ES/EN)

- Todo string visible usa `gettext`/`gettext_lazy`; nunca `_(variable)` (no extraíble).
- **Cadenas fuente en inglés**, aunque solo las vea un usuario chileno. El test falla con una sola tilde en un literal.
- Español **neutral, sin voseo** (nada de "podés/escribí/revisá"). Preferir impersonal ("conviene revisar") o trato de usted ("vuelva a probar"). Ningún test lo vigila: lo detectó el usuario.
- Escribir `msgid`/`msgstr` **a mano** en el `.po`. `makemessages` inventa traducciones `fuzzy` por parecido; tras cada corrida, `grep fuzzy`.
- `.mo` versionado: compilarlo localmente y commitearlo (el despliegue no corre `compilemessages`). Compilar con `--ignore .claude --locale es` o el `.mo` del proyecto puede quedar sin recompilar.
- `{% translate %}` **no** traduce un literal con `%(algo)s`: traducir en la vista y pasar por contexto.
- GNU gettext es obligatorio. `scripts/compile_translations.py` solo compila, no valida ni extrae.
- `apps/core/test_translations.py` vigila duplicados, vacíos, fuzzy, cadenas faltantes y fuente en español.

## 4. Git y ramas

- `main` siempre desplegable, nunca se toca directo. Rama por bloque: `codex/<área-o-bloque>` (no `feat/...`). Un PR por bloque con CI verde; no mezclar tooling con producto.
- `git fetch` antes de cualquier push y revisar `git log HEAD..origin/<rama>`. Si divergió: **nunca `push --force`**; rama nueva o fusión deliberada.
- `locale/es/LC_MESSAGES/django.mo` es binario: no se resuelve a mano, se regenera con `scripts/compile_translations.py` desde el `.po` fusionado.
- Conventional Commits. Al cerrar un bloque: `MASTER_PLAN.md` (✅), `CHANGELOG.md` `[Unreleased]`, `BACKLOG.md` si corresponde; la fila y el commit van juntos.

## 5. Calidad y CI

- Inicio: `uv sync --all-groups`. Gate: `pwsh scripts/verify.ps1` (check y `check --deploy`, `makemigrations --check`, `pytest -n auto --cov` con umbral en `pyproject.toml`, `ruff check`, `ruff format --check`, bandit, pip-audit).
- Iterar rápido: `uv run pytest apps/<app>/tests.py` y `uv run ruff check .`.
- **La suite corre en paralelo** (`-n auto`): los tests que escriben en disco usan `tmp_path` y apuntan `settings.DOCUMENTS_ROOT` ahí; los techos de consultas calientan la caché de `ContentType` antes de medir. Un fallo que solo aparece en paralelo se depura corriendo el archivo solo y sin `-n`.
- Tests dependientes de la fecha: fijar el reloj (`apps.core.testing.pin_today_mid_month`) y la fecha del dato; `scripts/pytest_clockshift.py` busca bombas de reloj.
- Ruff pinneado en `pyproject.toml` (0.15.22): una versión más nueva da cientos de avisos (`RUF012`, orden de imports) que no son deuda actual.
