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
  (desplegable de estado en permisos + fix de un bug real de navegación),
  **R2.1** (vista de edición de permisos, no existía), **R2.4** (el PDF
  DGAC ahora también se exige para `completed`, no solo `approved`) y
  **R2.6** (campo poblado/no poblado/mixto), y todo el **BLOQUE R3**
  salvo lo bloqueado en datos reales: **R3.2** (ordenamiento de listas) y
  **R3.3** completo — (a) operador archivado visible, (b) `contract_status`
  en `CostCenter` (decisión de negocio tomada en esta misma ventana, ver
  abajo), (c) investigado, ya estaba implementado. Nada de esto llegó a
  producción todavía.
- **709 tests verdes** (686 antes de R2.5; sumaron los de
  R2.5/R2.1/R2.4/R2.6/R3.2/R3.3, no hubo que restar nada). `ruff check .` y
  `ruff format --check .` también verdes. Catálogo `.po` regenerado tres
  veces con `makemessages -l es` (R2.4, R2.6, R3.3b): aparecieron fuzzy
  nuevos las tres veces (msgstr copiado de otro string por parecido, no por
  significado) — corregidos a mano antes de compilar, como advierte la nota
  de abajo.
- **`p340` estuvo sin internet gran parte del día** y volvió a tener acceso
  SSH hacia el final — no se llegó a desplegar antes de cerrar esta ventana.
- **Cinco migraciones nuevas sin aplicar en `p340`**: `workboard/0009`
  (`wip_limit`), `registry/0024` (`Operator.user`), `operations/0012`
  (choices en `PermissionHistory`), `operations/0013` (`area_type`, nula —
  no rompe los permisos ya cargados), `registry/0025` (`contract_status`,
  default "active" — no rompe los centros de costo ya cargados). El deploy
  con sudo (abajo) ya corre `migrate` — solo falta ejecutarlo.
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
- **R2.7** — `search_fields` de permisos solo busca `permission_number`
  pero el placeholder promete número/propósito/ubicación. Depende de R3.1.

**R1, R2.1, R2.4, R2.5, R2.6, R3.2 y R3.3 están completos.** Decisión de
negocio tomada 2026-08-07 para R3.3(b): "contrato cerrado" es un **eje
nuevo e independiente** de `is_active` — un CC con contrato cerrado sigue
en la lista normal (no se archiva), atenuado y agrupado después de los
operativos; `is_active` sigue siendo solo para archivar por error/duplicado.

**Todo lo que queda en R2 y R3 está bloqueado en datos reales de `p340`**,
no en trabajo de código: R2.2/R2.3 (folio interno, espera la restauración
del respaldo), R3.1/R3.1a (`report_purpose_mapping` tiene que correr contra
datos reales antes de escribir su migración) y R2.7 (depende de R3.1). El
siguiente bloque no bloqueado es **R4** (repositorio documental) — pero
revisar primero si de verdad no depende de R3.1/X.1 antes de arrancarlo.

Ver las filas correspondientes en `MASTER_PLAN.md` para el detalle de cada
fix, incluidos dos bugs reales encontrados y reproducidos en vivo que no
estaban en el plan original (el botón "Volver" de permisos/mantención/
vuelos necesitaba dos clics tras cualquier acción; `PermissionHistory`
mostraba estados en inglés crudo).

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
