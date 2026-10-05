# AeroControl — estado, emisión y mejora (2026-10-05)

> **No autoritativo.** Vista derivada del repo en `6fba910` (`p340` corre `66bc664`). Reemplaza al plan que estaba fuera del repo (`~/.claude/plans/distributed-cooking-axolotl.md`, no localizable). Si choca con `AGENTS.md`, `MASTER_PLAN.md` o `HANDOFF.md`, mandan ellos. Lo verificado leyendo código y documentos; **no se corrió la suite** en esta revisión.

## 1. Estado en una página

| Frente | Estado |
|---|---|
| Bloque 2 del plan del informe (`R3` + `UX-06`) | ✅ Hecho y desplegado desde 2026-09-02. Ya no es "lo siguiente". |
| Informe mensual `R0`–`R5`, narrativa (`LV-227`), PDF (`LV-263`), revisión previa (`LV-265`) | ✅ Desplegados |
| `R6` — XLSX y envío por correo | ⛔ Bloqueado: `EMAIL_HOST` vacío en `p340` |
| `R7` — bitácoras | ⛔ Depende de §6.6 de `apps/reporting/MAPPING.md` |
| `UX-30` — clasificador DAN 151 Ed. 4 | ⛔ Sin empezar; requiere tener el texto oficial |
| Plan maestro | 502 filas con estado: 458 hechas, 31 abiertas |

## 2. Emitir hoy el informe de septiembre (corte 30-sep)

El informe se emite el día 5. Todo lo necesario está desplegado; lo que falta es de operación, no de código.

**Pasos (en `p340`, con el entorno cargado con `set -a`):**
1. `manage.py generate_monthly_report --period 2026-09 --dry-run` y luego sin `--dry-run`. Es idempotente; congela el borrador pero **no aprueba**. `--force` emite una revisión nueva sin sobrescribir.
2. Abrir `/reporting/monthly/`, período septiembre.
3. Leer el bloque **«Revisar antes de emitir»** (cuatro avisos, no bloquean):
   - permiso vigente cuya faena no aparece en la tabla de cobertura;
   - faena nombrada en un hallazgo que no está registrada;
   - observación del período sin redactar;
   - total de faenas con operación distinto al del mes anterior.
4. Redactar hallazgos y observación del período (narrativa). Usar **Comparar** con el informe anterior.
5. **Aprobar** (deja el informe en solo lectura; queda registrado quién aprobó). Si hay que corregir, se emite una revisión nueva.
6. **Descargar PDF** del informe y del Dato Ejecutivo, y enviarlos manualmente: el envío automático no funciona hasta configurar el correo.

**Decisiones tuyas antes de aprobar:**
- **`CC716`**: contrato cerrado con el permiso `JEJ-2026-003` vivo hasta el 28-10. Es exactamente el caso del primer aviso (permiso vigente fuera de la cobertura). Reabrir el contrato o cerrar el permiso; si no, el informe firmado omite esa faena de la cifra «X de N».
- Redactar la narrativa: ningún código lo hace por ti.

## 3. Pendientes operativos (sin código, del `HANDOFF.md`)

1. `EMAIL_HOST` y credenciales en `/etc/aerocontrol.env` (desbloquea `R6` y todas las notificaciones).
2. Instalar los timers `letters`, `watchdog` y `verifybak` (`docs/scheduled-operations.md`). El vigilante no corre desde 2026-08-17.
3. Cablear el timer del informe mensual (disparo día 1 o 2).
4. Apagar la regla «Permisos: renovación vencida de plazo (T-15 · Gerencia)» (`LV-232`).
5. Asignar responsable a las faenas sin destinatario (11 de 15).
6. Metas de KPI y umbrales RMSE/GSD por contrato (decisión de negocio; no se inventan).

## 4. Mejora del repo: skills y diseño

**Skills a instalar (en una rama `codex/<área>`, una intención por rama):**

| Skill | Para qué | Cómo |
|---|---|---|
| `aerocontrol` (propia) | Navegar plan, convenciones y despliegue sin leer 5000 líneas | Copiar a `.claude/skills/aerocontrol/`; en `.gitignore` usar `.claude/*` + `!.claude/skills/` |
| `ponytail` (DietrichGebert) | `/ponytail-audit` sobre el repo y `/ponytail-review` en cada diff, contra sobreingeniería | `/plugin marketplace add DietrichGebert/ponytail` y `/plugin install ponytail@ponytail` |
| `ui-ux-pro-max-skill` | Mejora de diseño; ya en prueba con AeroConvert | Aplicar a AeroControl solo si la prueba sale bien |
| `engineering:tech-debt`, `engineering:code-review` | Priorizar las funciones largas y revisar PRs | Plugins de ingeniería |
| `design:accessibility-review`, `design:design-critique` | Revisión de pantallas y de la hoja A4 | Plugins de diseño |

**Orden propuesto:**
1. Marcar `UX-06` ✅ en `docs/ux-ui-plan.md` y comprobar `UX-02`, `UX-04`, `UX-05`, `UX-08`, `UX-10`, `UX-11`, `UX-22` (tienen rastro en el código, sin marca en el documento).
2. Archivar `HANDOFF.md` (3261 líneas): dejar solo el estado vigente y mover lo histórico a `docs/dev/handoff-archive.md`.
3. Test único que recorra las URLs y falle si una vista no declara `view_*` ni está en la lista de excepciones.
4. `/ponytail-audit` + `engineering:tech-debt` y decidir qué funciones largas valen refactor: `dashboard()` (364 líneas), `upcoming_expirations` (293), `panel_readiness` (214). Se descarta `api_openapi_schema` (Kanban dado de baja).
5. `T1.3`/`T1.4`: eliminar `pre_save` y auditoría atómica (trazabilidad ISO).

## 5. Paquete de revisión de diseño

Para que otra persona (o una skill de diseño) revise sin abrir el código:
- Capturas con el demo (`scripts/run-demo.ps1`, usuario `demo`) en tema claro y oscuro: panel, bandeja, lista de operadores, ficha de permiso, `/reporting/monthly/`.
- Las cinco hojas A4 impresas a PDF (informe) y el Dato Ejecutivo.
- Contrastes **calculados** (no leídos del navegador), como exige `AGENTS.md`.
- Vista móvil bajo 768 px de las listas con `UX-10`.
- Referencia: `docs/ux-ui-plan.md` (31 filas `UX-nn`) y el CSS `static/css/report-a4.css`.

## 6. Cómo mantener este plan vivo
`python .claude/skills/aerocontrol/scripts/plan_query.py --pending` da las filas abiertas reales. Este documento se regenera, no se edita fila por fila.
