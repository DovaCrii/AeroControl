# HANDOFF — AeroControl

## ✅ 2026-10-05 — PDF, confirmación única, revisión previa, regla de faenas y alertas, **desplegados** (`66bc664`)

`p340` corre **`66bc664`**, desplegado el 2026-10-05 (`git pull` `c1ed293..66bc664`,
reinicio, `git log` = `66bc664`). Lo que entró:

| Fila | Qué |
|---|---|
| deps | `pypdf` 6.19.0 y `urllib3` 2.8.0 (avisos de `pip-audit`). |
| `LV-263` | Botón **«Descargar PDF»** en el informe mensual y en el Dato Ejecutivo; impreso, 5 páginas y 1. |
| `LV-264` | Los botones con confirmación preguntaban **dos veces**; ahora una. |
| `LV-265` | Bloque **«Revisar antes de emitir»** en el informe (sólo pantalla). |
| `LV-266` | Regla única: una faena **cerrada o sin operación no entra en los registros**; el resumen de vencimientos deja de escribirle a las cerradas. |
| `LV-267` | **Alertas.** El resumen cae en Dirección si la faena no tiene responsable; los avisos a Dirección **ya no se pierden si un miembro no tiene correo** (ocho comandos); `check_client_letters` escribe a Dirección lo que escala y queda registrado. |

⚠️ **Dos despliegues de esta jornada "parecieron" correr sin el `git pull`**
(`collectstatic` copió 0 archivos y el `git log` seguía en el hash viejo). La
prueba de que llegó es siempre el hash final de `git log --oneline -1`.

### Falta, y es del usuario (sin código)

- **`EMAIL_HOST` y credenciales** en `/etc/aerocontrol.env`: hoy **ningún correo
  sale** (cuatro trabajos terminan «NO ENVIADO (correo sin configurar)»).
- **Instalar los timers `letters`, `watchdog` y `verifybak`**: el bloque está en
  `docs/scheduled-operations.md`. El vigilante no corre desde el 2026-08-17.
- **Apagar la regla «Permisos: renovación vencida de plazo (T-15 · Gerencia)»**
  (`LV-232` la mandó retirar; sigue activa con 3 alertas).
- **Poner responsable** a las faenas sin destinatario (11 de 15 el 2026-10-05).
- **`CC716`**: contrato cerrado con el permiso `JEJ-2026-003` vivo hasta el 28-10;
  reabrir el contrato o cerrar el permiso.
- Una contraseña quedó tecleada como comando en la terminal de `p340` el
  2026-10-05; el historial se borró con `history -c && history -w`.

## Historia

Las entradas anteriores (diseño del plan de mejora, incidentes, despliegues pasados, ramas resueltas) están en [docs/dev/handoff-archive.md](docs/dev/handoff-archive.md). **Cada despliegue deja una entrada nueva al principio de este archivo**; cuando ya no describa lo que corre en `p340` ni algo pendiente, se mueve al archivo.

## Punteros

| Para | Ir a |
|---|---|
| Trabajo pendiente y orden | `MASTER_PLAN.md` → "Rumbo a 1.0" |
| Contrato de trabajo + gotchas verificados | `AGENTS.md` |
| Cómo se resuelve una alerta (operación) | `docs/compliance-setup.md` |
| Diseño de las cláusulas ISO abiertas | `docs/dev/iso-r7-design-plan.md` |
| Contrato con AeroLink | `docs/dev/adr-0002-coexistencia-aerolink.md` |
| Plan de integración con AeroLink | `docs/dev/plan-integracion-aerolink.md` |
| Runbook de la VM | `docs/dev/ubuntu-vm-deploy.md` |
| Trabajos programados | `docs/scheduled-operations.md` |
| Qué cambió y cuándo | `CHANGELOG.md`, `git log` |
| Skill del proyecto (retomar sin leer 5000 líneas) | `.claude/skills/aerocontrol/` |
| Historia de este archivo | `docs/dev/handoff-archive.md` |
