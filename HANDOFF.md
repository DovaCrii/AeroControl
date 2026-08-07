# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) — sección **"Prioridades
> post-auditoría"**, al inicio del archivo. Este documento es solo el resumen
> de estado; el detalle de cada ítem vive en las filas de `MASTER_PLAN.md`.

## Estado al 2026-08-07 (noche)

- **`main` tiene commits sin desplegar.** El último deploy confirmado a
  `p340` fue el commit `8224373` (2026-08-05). Desde entonces se subieron
  B3.1/B3.2/B3.5, T5.7, todo el **BLOQUE R1** (5 bugs de la revisión en
  vivo, 3 corregidos + 2 investigados-no-reproducibles), y de **R2**: R2.5
  (desplegable de estado en permisos + fix de un bug real de navegación) y
  **R2.1** (vista de edición de permisos, no existía). Nada de esto llegó a
  producción todavía.
- **694 tests verdes** (era 686 antes de R2.5; R2.5 y R2.1 sumaron los que
  faltan — no hubo que restar nada). `ruff check .` y `ruff format --check .`
  también verdes.
- **`p340` estuvo sin internet gran parte del día** y volvió a tener acceso
  SSH hacia el final — no se llegó a desplegar antes de cerrar esta ventana.
- **Tres migraciones nuevas sin aplicar en `p340`**: `workboard/0009`
  (`wip_limit`), `registry/0024` (`Operator.user`), `operations/0012`
  (choices en `PermissionHistory`). El deploy con sudo (abajo) ya corre
  `migrate` — solo falta ejecutarlo.
- **Tres documentos de plan nuevos** (solo lectura, sin código):
  `docs/auditoria-iso-trazabilidad.md` (mapeo de las 14 cláusulas ISO),
  `docs/dev/adr-0002-coexistencia-aerolink.md` (contrato con la segunda app,
  AeroLink), y un PR ya abierto en `DovaCrii/AeroLink` (#31, plan revisado).

## Pendiente inmediato (antes de dar por cerrado el deploy)

Heredado de sesiones previas, **sigue sin confirmarse**:

```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py seed_document_types
```

Si dice `Ensured 10 document types (0 created)` ya está hecho; si dice
`(1 created)` recién quedó al día. Sin esto, "Autorización de Operación RPA
(DGAC aprobada)" no aparece en el desplegable y nadie puede aprobar un
permiso nuevo.

## Dónde retomar el trabajo de código

`MASTER_PLAN.md` → "Prioridades post-auditoría" tiene el orden completo.
Resumen de lo que sigue abierto en el **BLOQUE R2** (permiso de vuelo),
con las decisiones de negocio ya tomadas el 2026-08-07:

- **R2.2/R2.3** — folio interno **`JEJ-2026-001`** (correlativo anual,
  siempre presente desde la creación) + folio DGAC opcional; `__str__` usa
  el folio interno. **Requiere backfill sobre datos reales de `p340`** —
  el plan decidió que el importador/migración de datos reales corra
  **localmente contra una copia restaurada del respaldo**, lo que de paso
  sirve como el ensayo de restauración pendiente hace semanas. No aplicar
  esta migración directo en producción.
- **R2.4** — exigir el PDF oficial DGAC también para `completed` (hoy solo
  `approved`).
- **R2.6** — campo poblado/no poblado/mixto, obligatorio, sin exigencia
  documental adicional todavía.
- **R2.7** — `search_fields` de permisos solo busca `permission_number`
  pero el placeholder promete número/propósito/ubicación.

**R1, R2.1 y R2.5 están completos** (694 tests verdes). Ver las filas
correspondientes en `MASTER_PLAN.md` para el detalle de cada fix, incluidos
dos bugs reales encontrados y reproducidos en vivo que no estaban en el
plan original (el botón "Volver" de permisos/mantención/vuelos necesitaba
dos clics tras cualquier acción; `PermissionHistory` mostraba estados en
inglés crudo).

## Cómo desplegar (patrón establecido)

El usuario corre los comandos por su propia sesión SSH a `p340` y pega la
salida; Claude no tiene credenciales de producción ni debe manejarlas.

**Sin sudo:**
```bash
cd /opt/aerocontrol && git pull --ff-only && uv sync --frozen
```

**Con sudo** (pide la contraseña de sudo del usuario — no manejarla):
```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py migrate --no-input && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

**Verificación:**
```bash
sudo systemctl status aerocontrol --no-pager && git log --oneline -1
```

## Antes de tocar código

- Correr **`ruff check .` y `ruff format --check .`**, no solo `pytest` — el
  CI de GitHub (`ci.yml:26-27`) corre ambos.
- Tras editar el `.po`: revisar entradas `#, fuzzy` (gettext las genera al
  hacer `makemessages` y pueden traer una traducción incorrecta de otro
  string) antes de recompilar con `scripts/compile_translations.py`.
- Ver `MASTER_PLAN.md` → "Prioridades post-auditoría" para el orden vigente.
