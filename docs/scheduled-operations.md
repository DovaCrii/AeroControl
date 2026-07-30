# Operación programada

AeroControl tiene tres trabajos que deben ejecutarse solos. Cada ejecución
queda registrada en el modelo `JobRun` (comando, inicio, fin, resultado y un
resumen corto), así que después se puede comprobar si realmente corrieron.

| Comando | Qué hace | Frecuencia sugerida |
| --- | --- | --- |
| `generate_alerts` | Genera alertas de vencimiento y sus tareas de seguimiento en el tablero | Diario, temprano |
| `send_alert_digest` | Envía por correo el resumen de vencimientos a cada responsable de centro de costo | Diario, después de las alertas |
| `backup` | Crea un respaldo de la base con manifiesto y checksum | Diario, fuera de horario |
| `send_executive_report` | Envía el informe ejecutivo con KPIs del período vs el anterior y el XLSX adjunto | Semanal (lunes) |

El orden importa: `send_alert_digest` reporta lo que `generate_alerts` acaba de
detectar, así que conviene dejar un margen entre ambos.

`send_executive_report` va a los usuarios del grupo **Dirección** que tengan
correo, o a los que se indiquen con `--to`. Si no hay ninguno, el comando falla
con un mensaje claro en vez de enviar a nadie en silencio.

## Windows (Programador de tareas)

```powershell
./scripts/schedule_tasks.ps1 -EnvFile "C:/AeroControl_Data/.env"
```

Horas personalizables y desregistro:

```powershell
./scripts/schedule_tasks.ps1 -AlertsAt "06:30" -DigestAt "07:15" -BackupAt "22:00" `
  -ExecutiveReportDay Monday -ExecutiveReportAt "07:30"
./scripts/schedule_tasks.ps1 -Unregister
```

**`-EnvFile` es importante:** una tarea programada no hereda las variables de
tu sesión interactiva. Sin ese parámetro los trabajos usan los valores por
defecto del repositorio y pueden no encontrar la base de datos real ni la
configuración de correo.

Verificación:

```powershell
Get-ScheduledTask -TaskName 'AeroControl-*'
uv run python manage.py shell -c "from apps.core.models import JobRun; print(*JobRun.objects.all()[:10], sep=chr(10))"
```

El respaldo semanal completo (base + documentos a un disco externo) se registra
aparte con `scripts/register-backup-task.ps1`; ver `docs/dev/local-backup.md`.

## Linux (cron)

Con el repositorio en `/opt/aerocontrol` y las variables en
`/etc/aerocontrol.env`:

```cron
# m  h  dom mon dow  comando
  0  6   *   *   *   cd /opt/aerocontrol && set -a && . /etc/aerocontrol.env && set +a && uv run python manage.py generate_alerts >> /var/log/aerocontrol/cron.log 2>&1
  0  7   *   *   *   cd /opt/aerocontrol && set -a && . /etc/aerocontrol.env && set +a && uv run python manage.py send_alert_digest >> /var/log/aerocontrol/cron.log 2>&1
  0 21   *   *   *   cd /opt/aerocontrol && set -a && . /etc/aerocontrol.env && set +a && uv run python manage.py backup >> /var/log/aerocontrol/cron.log 2>&1
 30  7   *   *   1   cd /opt/aerocontrol && set -a && . /etc/aerocontrol.env && set +a && uv run python manage.py send_executive_report --period week >> /var/log/aerocontrol/cron.log 2>&1
```

`set -a` exporta las variables del archivo al entorno del comando, que es el
equivalente de `-EnvFile` en Windows. Igual que allá, cron arranca con un
entorno mínimo: si se omite, los trabajos no encontrarán la configuración.

## Linux (systemd — la VM p340)

En la VM el servicio ya corre bajo systemd con `User=levdigital01` +
`EnvironmentFile=/etc/aerocontrol.env` (systemd lee el archivo como root y luego
baja al usuario, así los trabajos reciben los secretos sin poder leer el
archivo). Los trabajos programados usan el mismo patrón con *timers*, más
robustos que cron para esto (`Persistent=true` recupera una corrida perdida si
la VM estaba apagada, y `journalctl` guarda la salida).

Crear los `.service` (oneshot) y `.timer` — un par por trabajo. Ejecutar como
root (pide `sudo`):

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
mkjob alerts "generate_alerts"          "*-*-* 06:00:00"
mkjob digest "send_alert_digest"        "*-*-* 07:00:00"
mkjob backup "backup"                   "*-*-* 22:00:00"
systemctl daemon-reload
systemctl enable --now aerocontrol-alerts.timer aerocontrol-digest.timer aerocontrol-backup.timer
'
```

Verificar y ver la próxima corrida:

```bash
systemctl list-timers 'aerocontrol-*' --all
```

Salida de la última ejecución de cualquiera de ellos:

```bash
journalctl -u aerocontrol-alerts.service -n 30 --no-pager
```

El informe ejecutivo semanal (`send_executive_report --period week`) se agrega
igual, con `OnCalendar=Mon *-*-* 07:30:00`, cuando haya destinatarios en el
grupo *Dirección*.

## Prueba antes de programar

`send_alert_digest` acepta `--dry-run`, que imprime destinatarios y conteos sin
enviar nada:

```powershell
uv run python manage.py send_alert_digest --dry-run
```

Si un centro de costo tiene vencimientos pero nadie a quien avisar, el comando
lo informa y continúa con los demás. El destinatario se configura en el
centro de costo: **Operador responsable** si es alguien del padrón de
operadores, o **Contacto externo** (nombre y correo) si es una persona ajena
al sistema RPA — un administrador, secretaría o un SSO. Si ambos están
configurados, se prefiere el operador; el contacto externo se usa cuando el
operador no tiene correo o quedó archivado.

## Correo

Sin `EMAIL_HOST` configurado se usa el backend de consola: el correo se imprime
en lugar de enviarse (útil en desarrollo, y evita que un despliegue a medio
configurar pierda avisos en silencio). Las variables están documentadas en
`.env.example`; nunca se versionan credenciales reales.
