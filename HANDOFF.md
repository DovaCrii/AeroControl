# HANDOFF — AeroControl

## ✅ 2026-10-19 — rediseño de toda la app, renovar permiso, asistente con registro y despliegue automatizado, **desplegados** (`7efc024`)

`p340` corre **`7efc024`**, desplegado el 2026-10-19 (respaldo `restorable.` → `git pull` + `uv sync` + `migrate` → `collectstatic` (17 copiados) + reinicio, `active`; hash leído de la salida pegada). Quedaron aplicadas `assistant.0001`, `geo.0007` y `operations.0033`.

**Seguimiento — fusionado sin desplegar: nada.**

Entró: `LV-307` a `LV-312` (portada, barra, panel, cabecera), `LV-315` a `LV-319` (tokens y olas A–D), `LV-320`/`LV-325` (renovar permiso con la misma área: copia del plan), `LV-321`/`LV-324` (plano técnico, portada con topografía, cabecera por módulo), `LV-322`/`LV-327` (`deploy_status` y `scripts/deploy.sh`), `LV-323`/`LV-326` (asistente acotado por empresa, registro de uso y topes en base; **sigue apagado en producción**), `LV-328` (ola E), `LV-329` (ruff 0.17 con las reglas fijadas a las de 0.15) y `LV-313` (Django 6.1.2).

**No verificado en producción:** que los fondos de módulo, la portada y el plano técnico se vean bien en pantalla real (el navegador integrado no compone animaciones); `scripts/deploy.sh` contra una VM real (no existía en la VM: se usó el plan B de cuatro bloques; **primer uso con `--dry-run`**); renovar un permiso real y el cierre de los avisos de 45/30 días.

**Pendiente — del usuario**
- Valores reales de `REPORT_CONTACT_ADDRESS` y `REPORT_CONTACT_WEB` en `/etc/aerocontrol.env` (hoy no están: los informes salen con textos de ejemplo).
- Probar el asistente en el demo con su llave y decidir licencia de NVIDIA o modelo propio (`PR 3` del asistente espera eso).
- Decidir si se limpia el historial de git (RUT, correos y un usuario Linux antiguo siguen en commits anteriores).
- Skills: `lecciones.md`, `rumbo-1.0.md`, `despliegue-p340.md` y `AGENTS.md` l.236.
- Ramas respaldadas a revisar: `codex/skill-aerocontrol`, `codex/t1-4-auditoria-visible`; y dos worktrees antiguos con un archivo sin commitear (`fervent-dhawan`, `keen-wilbur`).

**Pendiente — del código:** adoptar las reglas nuevas de ruff (533 hallazgos), chips de SIGO/mantenciones que no filtran por faena, informes con `.page-header` propio (sin fondo de módulo), `style=` en línea y ~225 colores sueltos de `app.css`.

## ✅ 2026-10-16 — rediseño de barra y panel, asistente con tope, Django 6.1.2, **desplegados** (`a807eb8`)

`p340` corre **`a807eb8`**, desplegado el 2026-10-16 en cuatro bloques (estado → entorno → `git pull` + `uv sync` → `collectstatic` + reinicio;
135 estáticos copiados, servicio `active`, hash leído de la salida pegada). **Sin migración** (la última sigue siendo `compliance/0027`).

**Seguimiento — fusionado sin desplegar: sólo documentación** (`LV-311` skill `pendientes-github`, `LV-314` recorte de skills; no afectan a producción) y `LV-327` (`scripts/deploy.sh`, sin migración ni estáticos; **sin probar aún en la VM**: el primer uso conviene con `--dry-run`).

Entró: `LV-307` (portada de dos paneles, tarjetas con barra, tipografía Archivo), `LV-308` (asistente: tope por usuario y hora, mensajes de límite/llave),
`LV-309` (barra lateral: un grupo abierto, activo con luz, nombres al enfocar), `LV-310` («Requiere atención», «Próximas mantenciones» en vez de la dona,
estados por texto), `LV-312` (cabecera con fondo aeronáutico propio y chips con acción) y `LV-313` (Django 6.1.2).

**Pendiente — del usuario**
- **`REPORT_CONTACT_ADDRESS` y `REPORT_CONTACT_WEB`** no están en `/etc/aerocontrol.env` (se quitaron el 2026-10-16 para no imprimir marcadores): los informes salen con los textos de ejemplo hasta que se fijen los reales.
- Revisar en producción con recarga forzada: portada, barra, panel (con y sin faena elegida) y la ficha de un informe impreso.
- Decisiones de skills: `lecciones.md`, `rumbo-1.0.md`, `despliegue-p340.md` y `AGENTS.md` l.236 (ver PR de `LV-314`).
- Ramas respaldadas en el remoto, a revisar: `codex/skill-aerocontrol`, `codex/t1-4-auditoria-visible`. Dependabot #93, #29 y #23 pedidos a recrear.
- Siguen los del 2026-10-13: limpiar o no el historial de git, probar el asistente en el demo con la llave propia, PDF real de la DGAC.
## 2026-10-13 — identidad visual, asistente con IA (prototipo), privacidad y estándar de trabajo (desplegados en `59e5ac6`)

`p340` corre **`59e5ac6`**, desplegado el 2026-10-13 por tandas (`ac173f3` → `dd66b63` → `b4f2372` → `59e5ac6`; cada
una con `git pull`, reinicio y `git log` = hash de `main`, leído de la salida pegada). Las dos de en medio llevaron
`collectstatic` (13 y 7 archivos); ninguna lleva migración (la última sigue siendo `compliance/0027`, del 2026-10-08).
El plan lo calcula `deploy_plan.ps1 -From <hash de la VM>`, y **el primer paso es leer el hash de la VM**: otra sesión ya
desplegó entre medias una vez.

**Seguimiento — fusionado sin desplegar: nada.**

Entró: `LV-298` («Registro de operaciones» con los rótulos del portal), `LV-299` (subir la autorización de la DGAC saca
las fechas del PDF), `LV-300` (la habilitación escrita en la ficha del operador cumple por **serie**), `LV-301` (la lista
de permisos abre con los últimos generados), `LV-302` a `LV-304` (**identidad visual**: capa global `identity.css`,
ilustraciones de AeroAcademy en estados vacíos y portada, dibujo de la aeronave por serie con hélices que giran, panel
lateral), `LV-305` (**asistente de consulta con IA, prototipo sólo demo**: en producción no existe), `LV-306` (datos
personales reales fuera del repositorio público) y el PR #86 (estándar de trabajo: `CLAUDE.md`, skills `orquestar` y
`revision-privacidad`, y el **escáner de privacidad** `tools/kit/privacy_scan.py` en el CI **y** en `scripts/verify.ps1`).

**Comprobado en producción tras el despliegue (2026-10-13):** `/assistant/` → **404** (el asistente no existe allí, como debe) y
`/health/` → **200**.

**Hecho en producción sin código (2026-10-08):** instalados los timers `letters`, `watchdog` y `verifybak` (15 timers
`aerocontrol-*`) y **apagada la regla** «Permisos: renovación vencida de plazo (T-15 · Gerencia)» (`enabled=False`); sus 3
alertas ya estaban cerradas desde el 2026-10-07.

**No verificado en producción:**
- La lectura del «Rango de fecha autorizado» de un PDF **real** de la DGAC (el patrón sale de una captura; si no lo lee, la
  aprobación sigue pidiendo las fechas a mano).
- «Registro de operaciones» con una operación real y una aeronave (en el demo ningún permiso las tiene; el alta la cubren las
  pruebas, no se vio en pantalla).
- La identidad visual **en pantalla ancha**: se revisó en un panel angosto (la portada y la ruta del panel sólo aparecen ≥ 768 y
  ≥ 1100 px).
- **El asistente contra el servicio real de NVIDIA:** las pruebas usan un cliente falso y no hubo llave en la sesión.
- El hemisferio de Punto Centro contra el portal, y si se corrió `scripts/activar-sync-baterias.sh` (de otra sesión).

**Pendiente — del usuario**
- **Decidir si se limpia el historial de git** (`LV-306`): los cinco RUT y los correos reales **siguen en commits anteriores**
  del repositorio público; borrarlos del código no los saca de ahí. Reescribir historia compartida no se hace sin su orden.
- **Probar el asistente con su llave del Developer Program** (`docs/dev/asistente-ia.md`; la llave sólo en su terminal, nunca en el
  chat ni en el repo). Ese acceso es sólo para prototipos: **producción exige licencia o alojar el modelo**.
- **Fotos de equipos con derecho de uso** en `static/img/equipment/<serie>.webp` (hoy hay dibujos propios; no se usan imágenes de
  buscadores ni de DJI).
- **Captura de Punto Centro del portal real** (lat/lon visibles), para decidir si la casilla «Hemisferio» se quita o se queda.
- **`T1.4` paso 3**: encender `AUDIT_FAIL_CLOSED=True`, **sólo tras una semana con la marca de fallos de auditoría en cero** y
  midiendo antes con `scale_readiness`.
- **Correo** (de lado a pedido del usuario): `EMAIL_HOST` y `SITE_BASE_URL`; sin eso ningún aviso sale.
- Dejados como están a pedido del usuario: responsable en 11 de 15 faenas, `CC716`, `LV-150` y `LV-228`.
- Decisiones de contenido del rediseño: un pie del panel lateral con usuario y resumen vivo, y los seis ítems retirados del menú
  (`docs/ux-ui-plan.md` §1); fase siguiente (fichas de detalle de documentos y solicitudes SIGO, formularios, informes impresos).
- Si un permiso aprobado debe contar como vigente desde la aprobación y no desde su fecha de inicio: cambia una cifra firmada y
  **no** se decidió (`LV-258`, `LV-296`).

**Pendiente — del código, sin decisión nueva**: ninguno. Lo que queda en `MASTER_PLAN.md` (`T1.1`, `T1.2`, `T1.5`, `T3.5`,
`X.4`, `X.5`, `LV-233`, `LV-245`) espera una decisión, es un refactor grande o depende de AeroLink, y el proyecto está en pausa
de estabilización.

## ✅ 2026-10-07 — modalidades SIGO, orden por columna, colores, prevuelo, auditoría, **desplegados** (`186dffb`)

`p340` corre **`186dffb`**, desplegado el 2026-10-07 por tandas (`97e2f35` → `120f5c8` → `ea480af` →
`b02d84e` → `23e7b48` → `186dffb`; cada una con `git pull`, reinicio y `git log` = hash de `main`, leído
de la salida pegada). Tres migraciones, cada una con respaldo `verify_backup` = *restorable* antes:
`operations/0030` (`area_modality`, `vertices`), `operations/0031` (`approx_flight_minutes`) y
`operations/0032` (el chequeo prevuelo sin vuelo). Entró: `LV-277` (el centro sigue a la circunferencia y
el arrastre vuelve a guardarse), `LV-278` bloques A y B (Punto Centro, Corredor, Triangular,
Cuadricular; la hoja sigue el portal), `LV-279` (números cerrados), `LV-280` (orden por columna),
`LV-281` y `LV-284` (panel: «Esperando» en naranja; menú sin «¿Puedo volar?» ni «Vuelos»), `LV-282`
(color por capa), `LV-283`, `LV-286` (meteorológica informativa), `LV-287` (el permiso no pasa del
seguro), `LV-288` (el orden se conserva al filtrar, vacíos al final, «Estado» por lo que se ve),
`LV-238` (el chequeo prevuelo antes de volar), `T1.4` pasos 1 y 2 (el fallo de auditoría se ve, y la
auditoría atómica **apagada por omisión**) y `LV-289` (la skill `/terminar-bloques`).

**Seguimiento — fusionado sin desplegar: nada.** (Regla desde 2026-10-07: se fusiona bloque tras bloque y
se despliega **una vez** al final; ver `AGENTS.md` «Despliegue por tandas». Cuando algo quede fusionado
sin desplegar, va **aquí**, con qué lleva migración y qué lleva estáticos; los comandos justos los escribe
`.claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash de la VM>`.)

⚠️ **Ojo con `LV-287`:** los permisos solicitados ya guardados que pasen del seguro de sus aeronaves no se
rompen, pero fallarán al editarlos hasta corregir la fecha.

**No verificado en producción** (se comprobó con pruebas y en el demo, no en `p340`): el arrastre con el
ratón real del editor y el clic sobre el selector de color; la hoja de SIGO contra el portal real; el
rojo/naranja de «Esperando» a ojo; el chequeo prevuelo antes del vuelo (pantallas y adopción) y la
pantalla «Cambio no guardado», que sólo aparece con `AUDIT_FAIL_CLOSED` encendido. Y `LV-273` sigue sin
ejercitarse allí (aún no hay solicitudes de vuelo reales: ahora, al separar un plan, se crean con
modalidad).

**Pendiente — del usuario**
- **`T1.4` paso 3**: **encender `AUDIT_FAIL_CLOSED=True`** en `/etc/aerocontrol.env` (decidido
  fail-closed el 2026-10-07; el paso atómico ya está en el código, apagado), **sólo tras una semana
  con la marca de fallos de auditoría en cero** y midiendo antes con `scale_readiness`.
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
