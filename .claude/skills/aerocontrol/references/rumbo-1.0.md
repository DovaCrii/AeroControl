# Rumbo a 1.0 — qué falta y qué decide el usuario

Fuente: `MASTER_PLAN.md` § "Rumbo a 1.0" (líneas 9–92, redactada el 2026-08-12) actualizada con la primera entrada de `HANDOFF.md` (2026-10-05, `p340` corre `66bc664`). **El estado cambia rápido: si esta lista choca con `HANDOFF.md`, manda `HANDOFF.md`.**

## Idea central
Lo que separa a la app de una 1.0 **ya no es código, es operación**. Los dos bloqueadores que `v0.4.0-beta` declaró (`T2.1`, `V.3`) están cerrados.

## Criterios de salida a 1.0 (estado al 2026-08-12/20)
| # | Criterio | Estado |
|---|---|---|
| 1 | CSP *enforcing* en `p340` | ✅ 2026-08-13 |
| 2 | Notificaciones llegando a personas reales | ❌ no llega nada: `EMAIL_HOST` vacío, los correos se imprimen en el journal (`LV-119`) |
| 3 | Importador `R4` con `--apply` real | Bloqueado por 3 carpetas de `Z:` |
| 4 | Ensayo de restauración como rutina | 🔄 la mitad automática corre a diario; falta cadencia escrita del ensayo completo |
| 5 | Monitoreo mínimo | 🔄 los trabajos avisan si se atrasan (`LV-114`); falta instalar su timer y cubrir "la VM está apagada" |
| 6 | 30 días estables sin incidente P0 | corre desde 2026-08-11 |
| 7 | Correo saliente con dominio corporativo (SPF/DKIM) | ❌ bloqueador del criterio 2 |

## Pendientes operativos del usuario (sin código) — HANDOFF 2026-10-05
- Configurar `EMAIL_HOST` y credenciales en `/etc/aerocontrol.env`: hoy ningún correo sale (cuatro trabajos terminan «NO ENVIADO (correo sin configurar)»).
- Instalar los timers `letters`, `watchdog` y `verifybak` (bloque en `docs/scheduled-operations.md`). El vigilante no corre desde el 2026-08-17.
- Apagar la regla «Permisos: renovación vencida de plazo (T-15 · Gerencia)» (`LV-232` la mandó retirar; sigue activa con 3 alertas).
- Asignar responsable a las faenas sin destinatario (11 de 15 el 2026-10-05).
- `CC716`: contrato cerrado con el permiso `JEJ-2026-003` vivo hasta el 28-10; reabrir el contrato o cerrar el permiso.

## Decisiones que solo toma el usuario (no inventar valores)
- Metas de KPI que faltan (precisión, tasa de re-vuelos, cumplimiento de plazos): sin ellas el indicador se muestra pero no marca incumplimiento. Se fija en `apps/compliance/kpis.py`.
- Umbrales RMSE/GSD por contrato (`R7.4`): sin ellos los entregables quedan "Sin evaluar". Se cargan desde la ficha del centro de costo.
- Alcance de la limpieza del Kanban (`LV-78`): una opción borra el registro de qué tarjeta cerró qué alerta.
- `LV-74`: las 10 vigencias que faltan en producción (lo único con impacto de cumplimiento hoy).

## Bloqueado por terceros
- `R4`: nombres de carpeta en `Z:` y antivirus real (instalado y verificado en agosto).
- `X.4` (ingesta de vuelos): AeroLink está en M0 y las sesiones son M3; la mitad de baterías se cerró con `X.4b`.

## Diferido por diseño (no ejecutar sin instrucción explícita)
Bloque 3 (UX Kanban), Bloque 5 salvo `JobRun`, Bloque 6.3 (asistente IA), DJI Cloud API (`T6.7`), Celery, Gantt (`LV-6`, obsoleto), IPER estructurado de `R7.5` (solo a pedido), migrar a PostgreSQL (cuando AeroLink lo instale en la misma VM, con un ADR).

## Deuda técnica: política incremental
`core/views.py` y `registry/views.py` son grandes, pero el riesgo de una migración XL supera su beneficio con uso diario real. **Extraer mixins/selectors solo al tocar el flujo por otra razón** (como `EffectivenessVerificationMixin` y `StatusFlowMixin`, extraídos al aparecer su segundo usuario). Pendientes de arquitectura con ID: `T1.1`–`T1.5`, `T3.5`, `T4.5`.

## Cuándo regenerar este archivo
Cuando cambie el criterio de salida o cierre un pendiente operativo. Para el estado de filas usar `plan_query.py --pending`, no este archivo.
