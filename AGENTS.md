# AeroControl — guía para agentes (Codex / Claude Code)

## Objetivo

Aplicación Django local-first para coordinar operaciones de aviación (flota RPA/UAS, operadores, cumplimiento DGAC, mantenimiento, permisos de vuelo, Kanban). La seguridad, trazabilidad y consistencia de datos prevalecen sobre cambios cosméticos. El proyecto está en **pausa de estabilización**: no se agrega funcionalidad nueva fuera de lo definido en `MASTER_PLAN.md` sin que el usuario lo pida explícitamente.

**Decisión de despliegue ya tomada (no reabrir sin que el usuario lo pida):** la aplicación se mantiene como web en servidor interno (intranet), no como app de escritorio. PostgreSQL se adopta cuando haya usuarios concurrentes reales (ver `docs/postgresql-readiness.md`); no migrar antes.

> **Si existe `HANDOFF.md` en la raíz, léelo antes que nada.** Describe una
> situación puntual sin resolver (por ejemplo un merge pendiente) que condiciona
> lo que se puede hacer. Se borra cuando queda resuelta; su ausencia significa
> que no hay nada excepcional y se puede ir directo a `MASTER_PLAN.md`.

## Trabajo en paralelo

Puede haber **otra sesión de agente empujando a la misma rama**. Ocurrió el
2026-07-24: dos líneas arreglaron el mismo P0 por separado. Por eso:

- `git fetch` **antes** de cualquier push, y revisar `git log HEAD..origin/<rama>`.
- Si la rama divergió, **nunca** `push --force`: empuja a una rama nueva o
  fusiona deliberadamente. Sobrescribir el trabajo de otro no es reversible.
- Al fusionar, `locale/es/LC_MESSAGES/django.mo` es **binario**: no se resuelve a
  mano, se regenera con `scripts/compile_translations.py` desde el `.po` fusionado.

## Precedencia documental

Cuando dos documentos parezcan contradecirse, este es el orden de autoridad:

`AGENTS.md` (este archivo) > `MASTER_PLAN.md` (qué hacer y en qué orden) > `openspec/changes/*` (spec del bloque en curso) > `AUDIT_CLAUDE.md` (evidencia técnica) > `BACKLOG.md` (registro histórico) > `README.md` / `ARCHITECTURE.md` > `docs/*.md` > `docs/dev/*.md` (notas internas, no autoritativas — pueden estar desactualizadas).

Si un plan externo (por ejemplo un archivo que el usuario suba fuera del repo) propone una convención que choca con lo ya establecido aquí — nombres de rama, umbrales, estructura de carpetas — se reconcilia a favor de lo ya vigente en el repo, y se deja constancia del ajuste en el PR o en `MASTER_PLAN.md`, no se cambia esta guía en silencio.

## Flujo de trabajo Git

- `main` siempre desplegable. Nunca se modifica directamente.
- Una rama por bloque de trabajo: `codex/<area-o-bloque>` (p. ej. `codex/repo-hygiene`, `codex/alertas-kanban`). No usar `feat/...` ni otros prefijos — esta es la convención real del repo.
- Un PR por bloque, con CI verde. No mezclar bloques ni intenciones distintas en el mismo PR/commit (ver deuda histórica del commit `980b763` en `AUDIT_CLAUDE.md`, que mezcló tooling vendorizado con correcciones de traducción — no repetir ese patrón).
- Usa `uv sync --all-groups` al empezar. Antes de entregar, `scripts/verify.ps1` debe pasar completo (ver sección de calidad).
- Define `DB_PATH`, `DOCUMENTS_DIR`, `LOGS_DIR` y `BACKUPS_DIR` fuera del repositorio. Nunca confirmes datos operativos, documentos, backups ni secretos reales.
- Para cambios de modelo, crea y revisa la migración generada (nombre descriptivo, no el autogenerado por Django si es ambiguo); incluye pruebas de regresión para la regla de negocio que motiva el cambio.
- Cada bloque cerrado actualiza `MASTER_PLAN.md` (marcar la tarea ✅), añade su entrada a `CHANGELOG.md` (`[Unreleased]`) y, si corresponde, `BACKLOG.md`.

## Convenciones de dominio (no negociables)

- `apps.core.BaseModel`: UUID como PK, `created_at`/`updated_at`, `is_active` para archivado lógico — **nunca borrar filas operativas**, archivar. `notes` para contexto opcional.
- ForeignKeys operativos usan `on_delete=PROTECT` salvo justificación explícita documentada en el PR (ver `AUDIT_CLAUDE.md` F-07 sobre los `CASCADE` que hay que corregir — no introducir más).
- Lógica de negocio en modelos ("fat models, thin views"). Nada de reglas de negocio en templates, forms-only (sin espejo en `clean()`/constraint) ni serializers — ver `ARCHITECTURE.md`.
- Interfaz bilingüe ES/EN: todo string visible al usuario usa `gettext`/`gettext_lazy`, nunca texto crudo ni `_(variable)` (no extraíble por `makemessages`). **Las cadenas fuente se escriben en inglés**; el español vive en el catálogo, nunca en el código.
- **GNU gettext es obligatorio** (`scoop install gettext` en Windows, `apt install gettext` en Linux). Sin él `makemessages` no corre y el catálogo se desincroniza en silencio: así se acumularon 29 cadenas rotas y 26 msgid duplicados que impedían a `msgmerge` funcionar. El flujo es `makemessages -l es` → traducir → `compilemessages -l es`. `scripts/compile_translations.py` solo compila; **no valida ni extrae**, así que no sustituye a gettext.
- `apps/core/test_translations.py` vigila la deriva sin depender de gettext: falla si hay msgid duplicados, entradas vacías o *fuzzy* (Django ignora las fuzzy, así que salen en inglés), cadenas del código ausentes del catálogo, diferencias de solo mayúsculas, o cadenas fuente escritas en español.
- Auditoría: toda mutación autenticada relevante debe quedar en `AuditEvent` (append-only) vía `apps.core.audit.set_audit_context` en la vista.

## Contrato de permisos y lectura (obligatorio en toda vista nueva)

- Vistas mutantes (crear/editar/borrar/transición de estado) exigen el permiso `add_*`/`change_*`/`delete_*` correspondiente.
- **Toda vista de lectura (listado, detalle, exportación, API) exige `view_*` explícito** — no basta `LoginRequiredMixin` a secas. Este es el gap que produjo los hallazgos F-05/F-06 de `AUDIT_CLAUDE.md` (documentos y calendario legibles sin permiso de dominio); no repetirlo.
- Si el modelo tiene o debería tener aislamiento por `tenant`/`OperationalTenant`, la vista debe acotar el queryset por tenant del usuario, no solo por permiso de modelo (ver F-08 sobre el estado real, hoy incompleto, de esa garantía).
- **Toda vista nueva debe tener una prueba de 403** para un usuario sin el permiso correspondiente, y si aplica, una prueba de aislamiento cross-tenant.
- No uses `fields = "__all__"` en formularios de escritura.
- Valida relaciones de dominio en formularios **y** en modelos (`clean()` o `CheckConstraint`) — no solo en el formulario, que es evadible desde el admin, la API o un import.
- No interpoles JSON controlado por usuarios con `|safe`; usa `json_script`.
- Las exportaciones (CSV/XLSX/DOCX) deben neutralizar fórmulas y limitar campos a datos aprobados — reutiliza `CsvExportMixin`, no reimplementes la neutralización.

## Definition of Done por tipo de cambio

| Tipo de cambio | Mínimo exigido |
|---|---|
| Modelo nuevo/campo nuevo | Migración con nombre descriptivo + `CheckConstraint`/`UniqueConstraint` si aplica + prueba de la constraint |
| Vista nueva | Prueba de 403 sin permiso + prueba de scope de tenant si el modelo lo requiere + strings traducidos |
| Comando de management | Prueba de camino feliz + prueba de camino de error (no solo `CommandError` trivial) |
| Formulario | Prueba por cada regla de `clean()`/`add_error` |
| Corrección de bug | Prueba que falla sin el fix y pasa con él (ver commits `7dc4151`/`86c57ce` como ejemplo) |
| Cambio de plantilla | Confirmar que `apps/core/test_templates.py` sigue verde (compila) |

## Calidad obligatoria antes de cada commit/PR

Gate canónico (debe pasar completo, y ahora sí falla si algo se rompe — ver `scripts/verify.ps1`):

```powershell
pwsh scripts/verify.ps1
```

Para iterar rápido dentro de una app, sin esperar el gate completo:

```powershell
uv run pytest apps/<app>/tests.py
uv run ruff check .
```

El gate completo corre: `manage.py check` (+ `--deploy`), `makemigrations --check --dry-run`, `pytest --cov=apps` (falla bajo el umbral de `pyproject.toml`, hoy 83%), `ruff check`, `ruff format --check`, `bandit`, `pip-audit`.

## Referencias

- Plan de trabajo y seguimiento por bloques: `MASTER_PLAN.md` (fuente de verdad de qué sigue).
- Auditoría técnica con evidencia: `AUDIT_CLAUDE.md`.
- Arquitectura: `ARCHITECTURE.md`.
- Registro histórico de lo entregado: `BACKLOG.md` y `CHANGELOG.md`.
- Specs de cambios en curso: `openspec/changes/`.
- Puesta en marcha: `README.md` y `scripts/setup.ps1`.
- Documentación de producto: `docs/` (raíz). Notas internas/históricas: `docs/dev/` (no autoritativas).
