# HANDOFF — AeroControl

## ✅ 2026-10-07 — modalidades SIGO, orden por columna, colores, auditoría visible, **desplegados** (`b02d84e`)

`p340` corre **`b02d84e`**, desplegado el 2026-10-07 por tandas (`97e2f35` → `120f5c8` → `ea480af` →
`b02d84e`; cada una con `git pull`, reinicio y `git log` = hash de `main`). Dos migraciones, cada una con
respaldo `verify_backup` = *restorable* antes: `operations/0030` (`area_modality`, `vertices`) y
`operations/0031` (`approx_flight_minutes`). Entró: `LV-277` (el centro sigue a la circunferencia y el
arrastre vuelve a guardarse), `LV-278` bloques A y B (Punto Centro, Corredor, Triangular, Cuadricular;
la hoja sigue el portal), `LV-279` (números cerrados), `LV-280` (orden por columna, 20 listas),
`LV-281` y `LV-284` (panel: «Esperando» en naranja; menú sin «¿Puedo volar?» ni «Vuelos»),
`LV-282` (color por capa), `LV-283` y `T1.4` paso 1 (el fallo de auditoría se ve en el centro de
administración).

**Seguimiento — fusionado sin desplegar: nada.** (Regla desde 2026-10-07: se fusiona bloque tras bloque
y se despliega **una vez** al final; ver `AGENTS.md` «Despliegue por tandas». Cuando algo quede
fusionado sin desplegar, va **aquí**, con qué lleva migración y qué lleva estáticos.)

**No verificado en producción** (se comprobó con pruebas y en el demo, no en `p340`): el arrastre con el
ratón real del editor y el clic sobre el selector de color; la hoja de SIGO contra el portal real; el
rojo/naranja de «Esperando» a ojo. Y `LV-273` sigue sin ejercitarse allí (aún no hay solicitudes de vuelo
reales: ahora, al separar un plan, se crean con modalidad).

**Pendiente — del usuario**
- **Decisión de `T1.4`**: ¿fail-closed (sin auditoría no se guarda) o fail-open ruidoso? El paso atómico
  espera esa respuesta; el paso 1 ya está desplegado.
- **Correo** (de lado a pedido del usuario): `EMAIL_HOST` y `SITE_BASE_URL`; sin eso ningún aviso sale.
- **Timers** `letters`, `watchdog` y `verifybak`: el bloque está en `docs/scheduled-operations.md`.
- **Apagar la regla** «Permisos: renovación vencida de plazo (T-15 · Gerencia)».
- **Responsable** en 11 de 15 faenas; **`CC716`** (contrato cerrado con el permiso `JEJ-2026-003` vivo
  hasta el 28-10); **`LV-150`** (decisión vencida el 2026-09-30); **`LV-228`** (cuatro operadores sin
  faena: René Herrera Molina, Natalia Ramos Mora, Jimmy Patricio Andrade Muñoz y David Vidal Vidal).
- Los textos de ayuda de los «?» del portal de SIGO, sólo si se quieren copiar a la app.

**Pendiente — del código, sin decisión nueva**: ninguno. Lo que queda en `MASTER_PLAN.md` (`T1.1`,
`T1.2`, `T1.5`, `T3.5`, `X.4`, `X.5`, `LV-231`, `LV-238`, `LV-233`, `LV-245`) espera una decisión, es un
refactor grande o depende de AeroLink, y el proyecto está en pausa de estabilización.

## ✅ 2026-10-06 — insignias, historial de permisos y solicitudes, CI y skills, **desplegados** (`05f5e2c`)

`p340` corre **`05f5e2c`**, desplegado el 2026-10-06 (`git pull` `66bc664..05f5e2c`, reinicio,
`git log` = `05f5e2c`, `systemctl is-active aerocontrol` = `active`). Entró: `LV-268` (guardián de
permisos), `LV-269` (insignias ámbar con niveles de severidad), `LV-270` y `LV-273` (historial de
permisos y de solicitudes, atómico), `LV-271` (el CI vuelve a poder estar verde), `LV-272` (las
cuatro skills de flujo) y el plan de `T1.3`/`T1.4`. **Comprobado en producción**: el historial de un
permiso real pasó de 3 a 4 filas dentro de la transacción y volvió a 3 al deshacerla. `LV-273` no se
pudo ejercitar allí: todavía no hay solicitudes de vuelo en producción (la cubren sus 8 pruebas).

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
