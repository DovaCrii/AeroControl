# Runbook: AeroControl en una VM Ubuntu Server (host Windows 11 Pro)

Guía paso a paso para levantar AeroControl en una máquina virtual Ubuntu
Server 26.04, para uso interno de 1–2 personas de JEJ en la LAN. Mantiene el
diseño **local-first** de [backend-plan.md](backend-plan.md): Django + SQLite
(WAL), datos fuera del repositorio, sin exposición a internet.

> **Supuestos de esta guía** (elegidos el 2026-07-29): host **Windows 11 Pro**,
> hipervisor **Hyper-V**, guest **Ubuntu Server 26.04**, acceso por **Tailscale**
> (HTTPS con certificado válido, sin exponer a internet). Si cambian, ver las
> alternativas al final de cada sección.

> **Esto NO dispara el "production gate"** del backend-plan (que aplica a datos
> reales en un servicio remoto/internet). Pero la **disciplina de backup +
> restore probado** (B-01/B-02) importa *más* ahora: la SQLite deja de vivir
> solo en tu notebook.

---

## 0. El único "gotcha" real: Python 3.12

`pyproject.toml` fija `requires-python = ">=3.12,<3.13"`. Ubuntu 26.04 trae un
Python de sistema más nuevo (3.14). **No uses el Python del sistema.** El
proyecto ya usa `uv`, que instala y aísla el intérprete correcto:

```bash
uv python install 3.12
```

Todo lo demás (`uv sync`, `uv run …`) usa ese 3.12 automáticamente.

---

## Parte A — Crear la VM en Hyper-V (en el host Windows)

1. **Activar Hyper-V** (PowerShell como administrador; reinicia al terminar):
   ```powershell
   Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
   ```
2. **Switch de red "External"** (para que otros PCs de la LAN alcancen la VM; el
   switch "Default" es NAT y no sirve para eso). En *Hyper-V Manager → Virtual
   Switch Manager → New → External*, ligado a tu adaptador físico (Ethernet o
   Wi-Fi). Llámalo `LAN-External`.
3. **Crear la VM**: *New → Virtual Machine*, **Generación 2**, **4096 MB** de RAM
   (sin memoria dinámica para un server), conectada a `LAN-External`, disco
   **VHDX 25 GB** (dinámico está bien). Monta el ISO de Ubuntu Server 26.04.
4. **Antes de arrancar**: en *Settings → Security*, deja Secure Boot activo con
   plantilla **"Microsoft UEFI Certificate Authority"** (Ubuntu no arranca con la
   plantilla de Windows). En *Settings → Automatic Start Action*, elige **"Always
   start automatically"** para que el server vuelva solo tras reiniciar el host.
5. Instala Ubuntu Server (usuario p. ej. `aero`, OpenSSH activado). Anota la IP
   que tome de la LAN.

*Alternativa:* si prefieres no usar Hyper-V, **VirtualBox** con adaptador
**"Puente"** logra lo mismo. WSL2 es una opción más liviana pero no es una VM
completa; como bajaste el ISO de Server, esta guía asume la VM.

---

## Parte B — Preparar el guest (dentro de Ubuntu)

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git curl
# uv (gestiona Python 3.12 aislado)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv python install 3.12

# Código en /opt/aerocontrol (ajusta el remoto a tu repo)
sudo mkdir -p /opt/aerocontrol && sudo chown $USER:$USER /opt/aerocontrol
git clone <URL-DE-TU-REPO> /opt/aerocontrol
cd /opt/aerocontrol
uv sync

# Datos FUERA del repo (SQLite, documentos, respaldos, logs)
sudo mkdir -p /srv/aerocontrol-data/{db,documents,backups,logs,exports}
sudo chown -R $USER:$USER /srv/aerocontrol-data
sudo mkdir -p /var/log/aerocontrol && sudo chown $USER:$USER /var/log/aerocontrol
```

---

## Parte C — Configuración (`/etc/aerocontrol.env`)

Un solo archivo que cargan **el servicio web** y **los trabajos programados**,
ambos vía `systemd` (`EnvironmentFile=`, que sí puede leer un archivo 600 root
antes de bajar privilegios — ver Parte E y Parte G). Contiene el `SECRET_KEY`
y la clave de correo → **root, permisos 600, nunca al repositorio.**

Genera un `SECRET_KEY`:
```bash
cd /opt/aerocontrol
uv run python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Crea `/etc/aerocontrol.env` (`sudo`):
```ini
# Django usa 'dev' por defecto en manage.py; en la VM SIEMPRE prod.
DJANGO_SETTINGS_MODULE=config.settings.prod
DEBUG=False
SECRET_KEY=pega-aqui-el-generado

# Datos fuera del repo
DB_PATH=/srv/aerocontrol-data/db/aero_ops.sqlite3
DOCUMENTS_DIR=/srv/aerocontrol-data/documents
BACKUPS_DIR=/srv/aerocontrol-data/backups
LOGS_DIR=/srv/aerocontrol-data/logs
EXPORTS_DIR=/srv/aerocontrol-data/exports
DOCUMENTS_STORAGE_BACKEND=local

# Quién puede entrar. Con Tailscale, el nombre MagicDNS de la VM.
ALLOWED_HOSTS=aerocontrol.tuTailnet.ts.net,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://aerocontrol.tuTailnet.ts.net

# TLS la termina Tailscale y reenvía X-Forwarded-Proto=https; prod ya lo lee.
# Si sirvieras HTTP plano en la LAN (sin proxy), pon estas tres en False:
#   SECURE_SSL_REDIRECT=False
#   (y en ese caso las cookies Secure de V.12 no viajan por HTTP)

# Correo (opcional; sin EMAIL_HOST el digest se imprime en el log, no se envía)
# EMAIL_HOST=smtp.example.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=aerocontrol@jej.cl
# EMAIL_HOST_PASSWORD=clave-de-aplicacion
# EMAIL_USE_TLS=True
# DEFAULT_FROM_EMAIL=aerocontrol@jej.cl
# SITE_BASE_URL=https://aerocontrol.tuTailnet.ts.net
```
```bash
sudo chmod 600 /etc/aerocontrol.env
```

> `config.settings.prod` **exige** `ALLOWED_HOSTS` (si falta, arranca con error
> explícito). Las políticas de sesión/CSP endurecidas en V.10–V.12 ya vienen en
> `base.py`, no hay que configurarlas.

---

## Parte D — Inicializar la base y los estáticos

```bash
cd /opt/aerocontrol
# /etc/aerocontrol.env es 600 root (Parte C): como usuario normal, ". ..." da
# "Permission denied". Usa sudo cat + process substitution para exportar las
# vars a esta shell sin volverte root (y sin que archivos que crees aquí, como
# la SQLite del migrate, queden con dueño root).
#
# `set -a` NO es opcional (corregido 2026-08-11, la versión sin él estuvo mal
# meses): `source` sobre un archivo de líneas `CLAVE=valor` define variables de
# *shell*, no de *entorno*, así que un proceso hijo como `uv run python` no las
# ve. Sin esto, `manage.py` cae al default `config.settings.dev` de su
# `setdefault` y muere con `SECRET_KEY not found` -- que es como se descubrió.
# Es el mismo `set -a` que ya usan los ejemplos de cron en
# `docs/scheduled-operations.md`.
set -a; source <(sudo cat /etc/aerocontrol.env); set +a

# Verifica ANTES de migrar que el entorno es el correcto. Migrar con `dev` en
# lugar de `prod` es el error más caro disponible acá: apuntaría a otra base.
echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"   # debe decir config.settings.prod

uv run python manage.py migrate --no-input
uv run python manage.py bootstrap_roles
uv run python manage.py collectstatic --no-input
uv run python manage.py createsuperuser
```

> **`init_dgac_board` salió de este procedimiento (LV-78, 2026-08-13).** Estaba
> acá para que el botón "Crear tarea" de la lista de alertas no fallara por falta
> de tablero — pero ese botón se quitó en `LV-69b` y el tablero se dio de baja el
> 2026-08-12. Correrlo hoy **recrearía el tablero que se está retirando**, y en
> un despliegue se sigue el procedimiento, no la nota al pie: por eso se saca de
> la lista en vez de anotarse como "no correr". El comando sigue existiendo.

Para **traer tus datos reales** desde el notebook: copia el snapshot `.sqlite3`
verificado a `/srv/aerocontrol-data/db/aero_ops.sqlite3` **antes** del `migrate`
(el `migrate` lo pone al día). Copia los documentos a
`/srv/aerocontrol-data/documents/`. Nunca por GitHub.

---

## Parte E — Servicio web (systemd + gunicorn + whitenoise)

WhiteNoise sirve los estáticos desde el propio gunicorn, así que no hace falta
un servidor de estáticos aparte. Crea `/etc/systemd/system/aerocontrol.service`:

> **El usuario real en `p340` es `levdigital01`, no `aero`** (verificado
> 2026-08-11 leyendo `systemctl status aerocontrol` de la VM en producción:
> `ExecStart=/home/levdigital01/.local/bin/uv run gunicorn ...`). Este documento
> decía `aero` mientras `scheduled-operations.md` y el `scp` de respaldos usaban
> `levdigital01`; los ejemplos de abajo quedan con el valor correcto. Si copias
> esto a otra máquina, ajusta el usuario **y la ruta de `uv`**, que vive en su
> `$HOME`.

```ini
[Unit]
Description=AeroControl (gunicorn)
After=network.target

[Service]
User=levdigital01
WorkingDirectory=/opt/aerocontrol
EnvironmentFile=/etc/aerocontrol.env
ExecStart=/home/levdigital01/.local/bin/uv run gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 --workers 3 --timeout 60
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aerocontrol
systemctl status aerocontrol          # debe quedar "active (running)"
curl -sS http://127.0.0.1:8000/health/   # {"status": "ok", ...}
```

> `gunicorn` escucha en `127.0.0.1` (solo local); Tailscale lo publica hacia
> afuera. `config.wsgi` ya usa `config.settings.prod` por defecto.

---

## Parte F — Acceso para ti + 1 (Tailscale)

Da HTTPS con certificado válido y nombre estable, sin advertencias de
self-signed, y no expone nada a internet (queda dentro de tu tailnet).

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                 # abre el link para autenticar la VM
sudo tailscale serve --bg 8000    # publica https://<nombre>.ts.net → 127.0.0.1:8000
tailscale serve status            # muestra el nombre HTTPS público del tailnet
```

Pon ese nombre en `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` (Parte C) y reinicia:
`sudo systemctl restart aerocontrol`. La otra persona instala Tailscale en su
equipo, entra al mismo tailnet, y abre `https://aerocontrol.tuTailnet.ts.net`.

*Alternativas:* **Caddy** de reverse proxy con cert interno (hay que confiar la
CA en los 2 equipos, una vez). O **HTTP plano en la LAN** apuntando al puerto —
en ese caso `--bind 0.0.0.0:8000` y `SECURE_SSL_REDIRECT=False` +
`SESSION_COOKIE_SECURE=False` + `CSRF_COOKIE_SECURE=False` (deshace parte del
endurecimiento de V.12; por eso se prefiere Tailscale).

---

## Parte G — Trabajos programados (systemd timers)

`/etc/aerocontrol.env` es 600 root (Parte C). Un cron corriendo como `aero` no
puede hacer `. /etc/aerocontrol.env` (da "Permission denied"), y meter
`source <(sudo cat /etc/aerocontrol.env)` en la línea de crontab **tampoco
sirve**: cron no tiene TTY para la contraseña de `sudo`, así que esa línea
fallaría igual de silenciosa. Esto no es teórico — es el mismo gotcha que se
repitió en el deploy real de la VM p340 (ver `HANDOFF.md`), y ahí se resolvió
cambiando cron por **timers de systemd**: el `.service` lee
`EnvironmentFile=/etc/aerocontrol.env` como root y luego baja privilegios a
`User=levdigital01` para ejecutar el comando, así el proceso recibe los secretos
sin que ese usuario necesite leer el archivo directamente. Detalle completo y el patrón
`mkjob` en [scheduled-operations.md](../scheduled-operations.md#linux-systemd--la-vm-p340);
aquí, adaptado a las rutas de esta guía:

```bash
sudo bash -c '
mkjob() {  # $1=nombre  $2=comando manage.py  $3=OnCalendar
  cat >/etc/systemd/system/aerocontrol-$1.service <<EOF
[Unit]
Description=AeroControl $1
After=network.target

[Service]
Type=oneshot
User=levdigital01
WorkingDirectory=/opt/aerocontrol
EnvironmentFile=/etc/aerocontrol.env
ExecStart=/home/levdigital01/.local/bin/uv run python manage.py $2
EOF
  cat >/etc/systemd/system/aerocontrol-$1.timer <<EOF
[Unit]
Description=AeroControl $1 (scheduled)

[Timer]
OnCalendar=$3
Persistent=true

[Install]
WantedBy=timers.target
EOF
}
mkjob alerts  "generate_alerts"                        "*-*-* 06:00:00"
mkjob digest  "send_alert_digest"                      "*-*-* 07:00:00"
mkjob backup  "backup"                                 "*-*-* 22:00:00"
mkjob execrep "send_executive_report --period week"    "Mon *-*-* 07:30:00"
systemctl daemon-reload
systemctl enable --now aerocontrol-alerts.timer aerocontrol-digest.timer aerocontrol-backup.timer aerocontrol-execrep.timer
'
```

`EnvironmentFile=` exporta las variables (incluido `DJANGO_SETTINGS_MODULE`) al
proceso, que es lo que hace que `manage.py` use `prod` y encuentre la base.
Prueba sin enviar nada: `uv run python manage.py send_alert_digest --dry-run`.
Verifica con `systemctl list-timers 'aerocontrol-*' --all` y revisa la salida
de una corrida con `journalctl -u aerocontrol-alerts.service -n 30 --no-pager`.

Cada corrida queda en el modelo `JobRun`; revísalo con:
```bash
uv run python manage.py shell -c "from apps.core.models import JobRun; print(*JobRun.objects.all()[:10], sep=chr(10))"
```

---

## Parte H — Respaldo y ensayo de restauración (no opcional)

El `backup` diario (Parte G) escribe en `/srv/aerocontrol-data/backups` con
manifiesto y checksum. **Súmale dos cosas:** una copia fuera de la VM y un
ensayo de restauración probado — un respaldo nunca restaurado no es un
respaldo, es una suposición.

### H.1 — Copia fuera de la VM

Desde el notebook (Windows, OpenSSH ya viene incluido), traer el último
respaldo + su manifiesto a la misma carpeta de OneDrive que ya se usa para los
respaldos locales (ver `docs/backend-follow-up.md`), en una subcarpeta propia
para no mezclarlos con los snapshots del PC:

```powershell
$dest = "D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\p340"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
scp levdigital01@p340.tailccd107.ts.net:/srv/aerocontrol-data/backups/aero_ops_*.sqlite3 $dest
scp levdigital01@p340.tailccd107.ts.net:/srv/aerocontrol-data/backups/aero_ops_*.json $dest
Get-ChildItem $dest | Sort-Object Name -Descending | Select-Object -First 6
```

Repetir periódicamente (a mano por ahora; automatizar con el Programador de
tareas de Windows es un paso posterior, no bloqueante). Un respaldo que solo
vive en `p340` no sobrevive a perder la VM.

### H.2 — Ensayo de restauración

En `p340`, restaurar a una ruta de ensayo — **nunca** sobre
`/srv/aerocontrol-data/db/aero_ops.sqlite3`, que es la base en uso:

```bash
cd /opt/aerocontrol
ls -la /srv/aerocontrol-data/backups   # elegir el snapshot más reciente
uv run python manage.py restore_backup \
  /srv/aerocontrol-data/backups/aero_ops_<YYYYMMDD_HHMMSS>.sqlite3 \
  /srv/aerocontrol-data/restore-drill/aero_ops_drill.sqlite3
```

`restore_backup` ya verifica el checksum del manifiesto antes de copiar — si
falla ahí, el respaldo está corrupto y **eso también es un resultado válido
del ensayo** (mejor descubrirlo ahora que en una pérdida real).

Confirmar que la copia restaurada es una base real y legible, sin tocar la
`.env` de producción — se apunta `DB_PATH` solo para este comando puntual:

```bash
set -a && source <(sudo cat /etc/aerocontrol.env) && set +a
DB_PATH=/srv/aerocontrol-data/restore-drill/aero_ops_drill.sqlite3 \
  uv run python manage.py shell -c "
from apps.registry.models import Aircraft, Operator, CostCenter
print('aeronaves:', Aircraft.objects.count())
print('operadores:', Operator.objects.count())
print('centros de costo:', CostCenter.objects.count())
"
```

Los conteos deben coincidir con lo que se ve hoy en la app en vivo (12/41/12
al 2026-08-05, ver "Prioridades post-v0.4.0-beta" al inicio de
`MASTER_PLAN.md`). Si coinciden, el respaldo es restaurable de verdad.
Limpiar la copia de ensayo al terminar — contiene datos reales de la DGAC y no
debe quedar viva más de lo necesario:

```bash
rm -rf /srv/aerocontrol-data/restore-drill
```

Registrar el resultado (fecha, snapshot usado, conteos, si el checksum pasó)
en la tabla de evidencias de `docs/backend-follow-up.md` o en `HANDOFF.md`
para que quede trazado.

---

## Parte I — Verificación final

- `systemctl status aerocontrol` → active (running).
- `curl https://aerocontrol.tuTailnet.ts.net/health/` desde el otro equipo → 200.
- Login web con el superusuario; el sidebar y los gráficos cargan.
- Reinicia la VM y comprueba que el servicio vuelve solo.
- Tras 24 h, `JobRun` tiene filas `ok` de los trabajos diarios.

---

## Apéndice — Apoyarte con Codex / opencode

Puedes delegar la ejecución a un agente en la VM, con dos reglas:

- **Nunca pegues secretos en el prompt** (el `SECRET_KEY`, la clave de correo,
  tokens de Tailscale). Que el agente los **genere o lea en la máquina**; tú los
  colocas en `/etc/aerocontrol.env` a mano.
- **Paso a paso, no todo de una.** Dale este runbook como referencia y pídele una
  parte a la vez (A→I), revisando el resultado de cada `systemctl status` /
  `curl /health/` antes de seguir. Así un error queda acotado a su paso.

Prompt inicial sugerido: *"Sigue `docs/dev/ubuntu-vm-deploy.md` desde la Parte B.
Ejecuta un paso, muéstrame la salida, y espera mi visto bueno antes del
siguiente. No inventes valores para `/etc/aerocontrol.env`: cuando haga falta un
secreto, dime el comando para generarlo y lo pego yo."*
