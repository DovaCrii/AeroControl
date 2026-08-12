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

> ⚠️ **`p340` está un commit atrás del tag.** Se desplegó `f0527e6`; despues se
> corrigieron **LV-68/69/69b/70/71/73** en `main`. **`LV-73` es un P0 de pérdida
> de datos** (ver abajo), así que ese despliegue no es opcional.

### Qué corre solo en `p340`

7 timers de systemd: `alerts` (06:00), `digest` (07:00), `credentials` (07:30),
`backup` (22:00), `snapshot` (23:00), `monthly` (23:30, último día del mes),
`monthly-deadline` (08:00, día 15). **Falta `executive`** (LV-67).

Verificar: `systemctl list-timers 'aerocontrol-*' --no-pager`

## Pendientes inmediatos — empezar por acá

**1. Desplegar el delta (P0, incluye el arreglo de pérdida de datos LV-73).**
No hay migraciones nuevas.

```bash
ssh levdigital01@100.121.16.118
cd /opt/aerocontrol && git pull
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
uv sync && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

**2. Destinatarios de las notificaciones (LV-66).** Hoy tres funciones
(`send_executive_report`, `check_monthly_records`, `check_monthly_review_deadline`)
no llegan a nadie: el grupo `Dirección` sólo tiene a `aortega`, **sin correo**.

```bash
uv run python manage.py shell -v 0 -c "
from django.contrib.auth.models import Group, User
g = Group.objects.get(name='Dirección')
a = User.objects.get(username='aortega'); a.email='aortega@jej.cl'; a.save()
u, _ = User.objects.get_or_create(username='cmunoz', defaults={'email':'cmunoz@jej.cl'})
u.email='cmunoz@jej.cl'; u.save(); g.user_set.add(u)
print(list(g.user_set.values_list('username','email')))"
uv run python manage.py send_executive_report --dry-run   # debe listar 2
```

**3. Timer del informe ejecutivo (LV-67)** — nunca se programó. Crear el par
`.service`/`.timer` con el patrón de `docs/scheduled-operations.md`
(usuario `levdigital01`, `OnCalendar=Mon *-*-* 07:30:00`, comando
`send_executive_report --period week`).

**4. Títulos de planes geoespaciales (LV-70).** Informe → revisar las 2 líneas →
repetir con `--apply`:

```bash
uv run python manage.py refresh_geoplan_titles
```

**5. Revisar si el bug LV-73 borró vigencias.** Las fechas que ese bug destruyó
**no son recuperables desde la app**; el respaldo previo al despliegue
(`/srv/aerocontrol-data/backups/aero_ops_20260811_165707.sqlite3`) las tendría.

```bash
uv run python manage.py shell -v 0 -c "
from apps.registry.models import Aircraft, Operator
print('aeronaves sin seguro:', list(Aircraft.objects.filter(insurance_expiry__isnull=True).values_list('registration', flat=True)))
print('operadores sin vigencia:', list(Operator.objects.filter(credential_expiry__isnull=True).values_list('full_name', flat=True)))"
```

**6. CSP a *enforcing***: verificado en demo, falta la variable en `p340`.
Criterio de salida de `beta`.

**7. R4, bloqueado del lado del usuario**: corregir 2 nombres de carpeta en `Z:`
(`RPA-4647`, `RPA-4884`) y configurar un antivirus real
(`DOCUMENTS_ANTIVIRUS_COMMAND` está vacío en todos los ambientes) antes de correr
el importador con `--apply`.

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
