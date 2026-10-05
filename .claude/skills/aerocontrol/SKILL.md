---
name: aerocontrol
description: Guía operativa del repo AeroControl (Django, gestión de flota RPA/UAS, cumplimiento DGAC, J.E.J. Ingeniería). Úsala SIEMPRE que se trabaje en este repositorio -- retomar trabajo, elegir la siguiente tarea, implementar o corregir algo, revisar un PR, tocar traducciones/permisos/migraciones, o desplegar a la VM p340 -- aunque el pedido no mencione MASTER_PLAN, HANDOFF o AGENTS. Reemplaza leer MASTER_PLAN.md (1500+ líneas) y HANDOFF.md (3000+ líneas) enteros.
---

# AeroControl

Django 6.1 modular (Python 3.12, uv, SQLite, Bootstrap 5 + HTMX), desplegado en intranet (VM `p340`) con datos reales. Proyecto en **pausa de estabilización**: no se agrega funcionalidad fuera del plan sin pedido explícito del usuario.

## 1. Al empezar (en este orden, ~2 minutos)

1. `git branch --show-current`, `git status --short --branch` y `git log --oneline -5`. **La rama no se supone**: el 2026-10-05 diez commits cayeron en una rama que nadie miró y ninguno llegó a `main`.
2. Leer **solo la primera entrada** de `HANDOFF.md` (hasta el primer `---`/`##` siguiente). Describe qué corre en producción y qué falta. No leer el resto.
3. Estado del plan sin abrir `MASTER_PLAN.md`:
   ```
   python .claude/skills/aerocontrol/scripts/plan_query.py --summary
   python .claude/skills/aerocontrol/scripts/plan_query.py --pending
   python .claude/skills/aerocontrol/scripts/plan_query.py --id LV-267     # una fila concreta
   ```
4. Si hay que entender un área, abrir **solo** la sección que apunta `references/mapa-plan.md` (con `sed -n 'A,Bp'`).

## 2. Antes de implementar una fila pendiente

- **El tablero miente en las dos direcciones.** Un `⬜` puede estar hecho (pasó 5 veces) y un `✅` puede tener la premisa vencida. Hacer `grep` del código que la fila describe antes de escribir nada.
- **Un `⬜` bloqueado por decisión de negocio no se desbloquea programando.** Umbrales de contrato, límites de jornada y metas de KPI los define el usuario; no inventar números.
- **Un pendiente anotado en un test es una hipótesis**, no un diagnóstico: verificar la causa antes de actuar.
- Antes de agregar un método a una clase larga, listar los que ya tiene (`grep -n "^    def "`): una segunda definición silencia a la primera sin error.

## 3. Reglas no negociables (resumen; detalle en `references/convenciones.md`)

- Modelos: `BaseModel` (UUID, `created_at/updated_at`, `is_active`). **Nunca borrar filas operativas**: archivar. FKs operativos con `on_delete=PROTECT`.
- Lógica de negocio en modelos; nada en templates ni serializers. Validar en formulario **y** en `clean()`/constraint.
- **Toda vista de lectura exige `view_*`** (no basta `LoginRequiredMixin`), acota por tenant y lleva prueba de 403. Sin `fields="__all__"` en formularios de escritura. Sin `|safe` con datos de usuario (`json_script`).
- Cadenas fuente **en inglés** con `gettext`; el español vive en el catálogo, **neutral y sin voseo** (trato de usted o impersonal). Traducciones nuevas **a mano** en el `.po`, nunca aceptar `fuzzy`; recompilar el `.mo` (está versionado).
- Mutaciones relevantes quedan en `AuditEvent` vía `set_audit_context`. Exportaciones reutilizan `CsvExportMixin`.
- Una intención por rama y por commit; rama `codex/<área>`; **nunca `push --force`**; `git fetch` antes de empujar (puede haber otra sesión en la misma rama).

## 4. Definition of Done

| Cambio | Mínimo |
|---|---|
| Modelo/campo | Migración con nombre descriptivo + constraint + prueba de la constraint |
| Vista | Prueba de 403 + aislamiento por tenant + strings traducidos |
| Comando | Camino feliz + camino de error real |
| Formulario | Una prueba por cada regla de `clean()`/`add_error`; si agrega campo a `Meta.fields`, agregarlo a la plantilla |
| Bug | Prueba que falla sin el fix y pasa con él (romper el arreglo una vez para confirmarlo) |
| Plantilla | `apps/core/test_templates.py` sigue verde |

Gate antes de entregar: `pwsh scripts/verify.ps1` (check, migraciones, `pytest -n auto --cov`, `ruff check` **y** `ruff format --check`, bandit, pip-audit). Verificar en navegador antes de marcar `✅`.

## 5. Al cerrar una fila

El commit y su fila van **juntos**: marcar `⬜→✅` en `MASTER_PLAN.md`, entrada en `CHANGELOG.md` `[Unreleased]`, y si cambió algo operativo, `HANDOFF.md`. Comprobar con `plan_query.py --ghosts` (no debe haber IDs `LV-N` del log sin fila).

## 6. Entregar y desplegar

**El agente crea, verifica y fusiona sus PR con el CI verde; el usuario solo despliega** (decisión del 2026-10-05). Tres skills de flujo, en este orden:

1. `/cerrar-tarea <fila>` — la fila, el `CHANGELOG` y el `HANDOFF` con el commit.
2. `/verificar` — el gate (`pwsh scripts/verify.ps1`, que corre lo mismo que el CI).
3. `/abrir-pr` — rama `codex/…`, PR, espera del CI y fusión; termina comprobando que el hash llegó a `origin/main`.

Después, `/desplegar-p340` dicta los pasos **uno por bloque** y lee la terminal del usuario. Reglas completas en **`references/despliegue-p340.md`**: el primer comando es `git status --short --branch`, `git pull` no se omite, y la prueba de que llegó es el hash de `git log --oneline -1` en la VM. El agente no tiene SSH.

## Dónde mirar según la tarea

| Necesito… | Leer |
|---|---|
| Convenciones, permisos, i18n, DoD completos | `references/convenciones.md` |
| Trampas ya vividas (tests, UI, migraciones, service worker) | `references/lecciones.md` |
| Desplegar, diagnosticar un 500 post-despliegue | `references/despliegue-p340.md` y `/desplegar-p340` |
| Entregar un bloque (rama, PR, CI, fusión) | `/abrir-pr` |
| Cerrar una fila del plan | `/cerrar-tarea` |
| Correr el gate sin inundar el contexto | `/verificar` |
| Qué falta para 1.0 y qué decide el usuario | `references/rumbo-1.0.md` |
| Dónde está cada bloque del plan (líneas y estado) | `references/mapa-plan.md` |

Precedencia documental si dos fuentes chocan: `AGENTS.md` > `MASTER_PLAN.md` > `openspec/changes/*` > `AUDIT_CLAUDE.md` > `BACKLOG.md` > `README.md`/`ARCHITECTURE.md` > `docs/*.md` > `docs/dev/*.md` (no autoritativas).
