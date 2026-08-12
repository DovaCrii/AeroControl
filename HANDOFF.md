# HANDOFF — AeroControl

> **Resumen de estado, no bitácora.** La historia detallada vive en `git log`,
> `CHANGELOG.md` y las filas del tablero. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) → sección **"Rumbo a 1.0"**.
> Si este archivo vuelve a crecer a cientos de líneas de cierres de ventana,
> podarlo: se hizo el 2026-08-11 (de 900 a ~110) y el contenido no se perdió,
> se movió a donde correspondía.

## Estado al 2026-08-11

- **Versión:** `v0.5.0-beta` (etiquetada y pusheada). `main` = `origin/main`.
- **Gate:** `pwsh scripts/verify.ps1` verde (953 tests, ruff, bandit, pip-audit).
- **Bloques completos:** R1, R2, R3, R5, R6 · base ISO R7.1-R7.3 + diseños
  R7.4-R7.7 escritos · R8.1 · X.1-X.3.
- **Parcial:** R4 (importador listo, `--apply` nunca corrido).
- **AOC cargado en producción** ✅ (2026-08-11, por el usuario).
- **`p340` al día con `main`** ✅ (2026-08-12, incluye el arreglo P0 de `LV-73`).

### Qué corre solo en `p340`

**8 timers de systemd**, todos verificados corriendo: `alerts` (06:00),
`digest` (07:00), `credentials` (07:30), `executive` (lunes 07:30),
`backup` (22:00), `snapshot` (23:00), `monthly` (23:30, último día del mes),
`monthly-deadline` (08:00, día 15).

Verificar: `systemctl list-timers 'aerocontrol-*' --no-pager`

Notificaciones a `Dirección`: `aortega@jej.cl` + `cmunoz@jej.cl`.

## Pendientes inmediatos — empezar por acá

**1. Cargar 10 vigencias que faltan (LV-74).** Es lo único con impacto de
cumplimiento hoy. **No es un bug** — se verificó contra el respaldo que nunca
estuvieron cargadas. Importa porque **un `NULL` no genera alerta** (decisión
correcta de LV-29: un nulo significa "nunca se ingresó"), así que estos 10 son
invisibles para las alertas, el calendario y el reporte: el hueco no se anuncia.

- Sin `insurance_expiry` (seguro JAC): `RPA-2019`, `RPA-3696`, `RPA-7126`.
- Sin `credential_expiry` (credencial DGAC): René Herrera Molina, Natalia Ramos
  Mora, Jimmy Patricio Andrade Muñoz, David Vidal Vidal, Jose Luis Ogalde
  Henríquez, Luis Piña Tapia, Alberto Jesus Angel Milla.

Se cargan desde la ficha de cada aeronave/operador, o re-corriendo
`load_dgac_vigencias` con una captura completa.

**2. CSP a *enforcing***: verificado en demo, falta la variable en `p340`.
Criterio de salida de `beta`.

**3. Las 2 ramas `claude/*`** (ver abajo) — cuanto más se demore, más difícil el
rescate.

**4. R4, bloqueado del lado del usuario**: corregir 2 nombres de carpeta en `Z:`
(`RPA-4647`, `RPA-4884`) y configurar un antivirus real
(`DOCUMENTS_ANTIVIRUS_COMMAND` está vacío en todos los ambientes) antes de correr
el importador con `--apply`.

Después de esto, el trabajo de fondo son las **Sesiones B/C/D** de
`MASTER_PLAN.md` → "Rumbo a 1.0".

## Cómo desplegar

Secuencia completa y corregida en
[docs/dev/ubuntu-vm-deploy.md](docs/dev/ubuntu-vm-deploy.md) → Parte D.
Lo esencial y los dos errores que costaron tiempo el 2026-08-11:

- **El merge/push va en Windows** (`D:\I+D\AeroControl`); las ramas sólo existen
  ahí. El **deploy va dentro de la sesión SSH**: `/opt/aerocontrol` es ruta
  Linux y PowerShell la resuelve como `C:\opt\aerocontrol`.
- **El nombre DNS `p340.tailccd107.ts.net` no resuelve bien** (apunta a una IP
  pública ajena). Usar la IP de Tailscale: `ssh levdigital01@100.121.16.118`.
- **`set -a` no es opcional** al cargar el entorno, o `manage.py` cae a
  `config.settings.dev` y muere con `SECRET_KEY not found`:
  ```bash
  cd /opt/aerocontrol && git pull
  set -a; source <(sudo cat /etc/aerocontrol.env); set +a
  echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"   # debe decir prod
  uv sync && uv run python manage.py migrate --no-input
  uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
  ```
- Antes de una migración que imponga una restricción, **chequear los datos
  reales primero** con `values_list` (no `.all()`, que hace `SELECT *` de
  columnas que aún no existen). Ejemplo vigente en la Parte D del runbook.
- Tomar un respaldo (`manage.py backup`) y **verificarlo**
  (`verify_backup <ruta>`) antes de migrar.

## Punteros

| Para | Ir a |
|---|---|
| Trabajo pendiente y orden | `MASTER_PLAN.md` → "Rumbo a 1.0" |
| Contrato de trabajo + gotchas verificados | `AGENTS.md` |
| Cómo se resuelve una alerta (operación) | `docs/compliance-setup.md` |
| Diseño de las cláusulas ISO abiertas | `docs/dev/iso-r7-design-plan.md` |
| Contrato con AeroLink | `docs/dev/adr-0002-coexistencia-aerolink.md` |
| Runbook de la VM | `docs/dev/ubuntu-vm-deploy.md` |
| Trabajos programados | `docs/scheduled-operations.md` |
| Qué cambió y cuándo | `CHANGELOG.md`, `git log` |

## Ramas sin resolver

Dos ramas `claude/*` **no** están en `main` y tienen trabajo único (~1.300
líneas: pulido visual, barrido de traducciones, quitar el campo técnico `order`
de los formularios Kanban, huecos de exportación CSV). Son **anteriores** a los
bloques R y tocan archivos que `main` ya cambió → conflicto real si se mergean
así. Hay que decidir: rescatar, rehacer sobre la base actual, o descartar.

- `claude/amazing-bouman-1b3d09` (+5)
- `claude/beautiful-curie-4193f1` (+2)
