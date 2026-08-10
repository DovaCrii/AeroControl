# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) — sección **"Prioridades
> post-auditoría"**, al inicio del archivo. Este documento es solo el resumen
> de estado; el detalle de cada ítem vive en las filas de `MASTER_PLAN.md`.

## Estado al 2026-08-10

- **Desplegado y confirmado en `p340`, commit `e008748`.** Las cinco
  migraciones pendientes (`workboard/0009`, `registry/0024`,
  `operations/0012`, `operations/0013`, `registry/0025`) se aplicaron sin
  error, `collectstatic` corrió y `aerocontrol.service` está
  `active (running)`. Este commit incluye todo lo subido el 2026-08-07:
  B3.1/B3.2/B3.5, T5.7, **BLOQUE R1** completo (3 bugs corregidos + 2
  investigados-no-reproducibles), **R2.1/R2.4/R2.5/R2.6** y **BLOQUE R3**
  completo salvo lo bloqueado en datos reales (R3.1/R3.1a) — R3.2
  (ordenamiento de listas) y R3.3 completo (operador archivado visible,
  `CostCenter.contract_status`, `Aircraft.retired` verificado).
- **709 tests verdes** (686 antes de R2.5; sumaron los de
  R2.5/R2.1/R2.4/R2.6/R3.2/R3.3). `ruff check .` y `ruff format --check .`
  también verdes.
- **Tres documentos de plan nuevos** (solo lectura, sin código):
  `docs/auditoria-iso-trazabilidad.md` (mapeo de las 14 cláusulas ISO),
  `docs/dev/adr-0002-coexistencia-aerolink.md` (contrato con la segunda app,
  AeroLink).
- **AeroLink (repo separado) quedó estabilizado en esta misma ventana**: los
  tres PRs pendientes (#29 esquema+sondas, #30→#33 verificador de
  conectividad/licencia DJI, #31 revisión de plan + ADR-0002) están
  mergeados a `main`, CI verde, 18/18 tests. AL-101 y AL-102 cerrados en el
  tracker. **AL-003 confirmado con evidencia**: ni 443 ni 8883 responden
  desde afuera de la red Tailscale de `p340` — Tailscale Funnel no abre
  puertos, túnela saliente. Decisión tomada: **relay MQTT externo**. Hay un
  worker (cliente MQTT saliente) armado y con tests en la rama local
  `codex/relay-worker` de AeroLink, sin subir — AeroLink quedó aparcado, no
  es el foco de esta ventana.
- **✅ Ensayo de restauración de respaldos — hecho 2026-08-10, primera vez
  que se prueba de verdad.** `aero_ops_20260809_180019.sqlite3` verificado
  (checksum) y restaurado a una ruta de ensayo: 16 aeronaves, 41 operadores,
  14 centros de costo, 2 permisos de vuelo, todo legible por el ORM.
  Registro en `docs/backend-follow-up.md`. La copia restaurada queda en
  `D:\I+D\AeroOpsDesk_Data\restore-drill\aero_ops_drill.sqlite3` (datos
  reales de la DGAC — no debe quedar viva más de lo necesario).
- **✅ R2.2/R2.3 — folio interno correlativo, hecho 2026-08-10.**
  `internal_folio` (`JEJ-2026-NNN`) asignado en `save()` bajo
  `select_for_update()`; backfill probado primero contra la copia restaurada
  (`JEJ-2026-001`/`JEJ-2026-002`) antes de tocar el modelo en serio. `__str__`
  ahora devuelve el folio interno — cascada automática a lista, calendario,
  panel de vencimientos, ficha de CC y plan geo. 715 tests verdes, verificado
  en vivo contra el demo (folio interno siempre presente, "En proceso" cuando
  falta el folio DGAC). Sigo desatendido con R3.1/R3.1a y R4.

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

- **R3.1/R3.1a** — vocabulario cerrado de `purpose`. `report_purpose_mapping`
  corre contra la misma copia restaurada.
- **R2.7** — `search_fields` de permisos. Depende de R3.1.
- **R4** (repositorio documental) — el importador corre en modo informe
  contra la copia restaurada. Antes revisar si depende de R3.1/X.1
  (normalizar `serial_number`) para no reimportar.

**R1, R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R3.2 y R3.3 están completos.**
Decisión de negocio tomada 2026-08-07 para R3.3(b): "contrato cerrado" es un **eje
nuevo e independiente** de `is_active` — un CC con contrato cerrado sigue
en la lista normal (no se archiva), atenuado y agrupado después de los
operativos; `is_active` sigue siendo solo para archivar por error/duplicado.

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
