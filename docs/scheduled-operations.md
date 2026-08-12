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
| `notify_expiring_credentials` (opcional, LV-29) | Avisa por correo a **cada operador** de sus vigencias DGAC por vencer o ya vencidas (credencial + habilitaciones, ≤30 días) | Diario o semanal, si se quiere el aviso directo al operador |
| `check_monthly_records` (LV-30) | El último día del mes, crea la **revisión de cumplimiento** pendiente por cada centro de costo que voló y avisa al grupo Dirección (vuelos vs registros del mes) | Diario (actúa solo el último día 28/29/30/31) |
| `check_monthly_review_deadline` (R6.5) | El día 15, revisa las revisiones del mes anterior que sigan **pendientes** (nadie las marcó) y las escala al grupo Dirección en un segundo correo. No crea ni cambia ninguna revisión, solo persigue lo que quedó sin firmar | Diario (actúa solo el día 15) |
| `sync_batteries` (X.4b) | Espeja el inventario de baterías de AeroLink en `registry.Battery` (ciclos, salud, firmware) para la evidencia ISO 7.1.3. **Sólo se programa cuando AeroLink publique su endpoint**; hasta entonces se corre a mano con `--from-file`. Nunca borra: una batería ausente del feed se reporta, no se elimina | Diario, una vez que exista el endpoint |
| `check_flight_duty_limit` (R7.5) | Reporta al grupo Dirección los pilotos cuya **jornada de vuelo del día anterior** superó las **8 horas** (control de fatiga, ISO 45001 6.1.2). Sólo reporta: nunca edita ni rechaza un registro de vuelo | Diario |
| `check_alert_effectiveness` (R7.6) | Escala al grupo Dirección las acciones correctivas resueltas hace **30 días** cuya eficacia **nadie confirmó**. Nunca resuelve, reabre ni verifica por su cuenta: una máquina declarando que una acción correctiva fue eficaz es lo contrario de la evidencia que pide ISO 10.2 | Diario |
| `snapshot_compliance` (R7.7) | Guarda los totales documentales del día (una fila por centro de costo más una consolidada). **Sin esto el reporte no puede mostrar tendencia**: los contadores se evalúan siempre "a hoy", así que comparar período contra período marca "sin cambio" por construcción. Idempotente: repetir la misma fecha la sobrescribe, no duplica | Diario, al final del día |

El orden importa: `send_alert_digest` reporta lo que `generate_alerts` acaba de
detectar, así que conviene dejar un margen entre ambos.

`send_executive_report` va a los usuarios del grupo **Dirección** que tengan
correo, o a los que se indiquen con `--to`. Si no hay ninguno, el comando falla
con un mensaje claro en vez de enviar a nadie en silencio.

## Windows (Programador de tareas)

```powershell
./scripts/schedule_tasks.ps1 -EnvFile "C:/AeroControl_Data/.env"
```

El script registra `GenerateAlerts`, `AlertDigest`, `Backup`, `ExecutiveReport`,
`MonthlyRecords` (LV-30, cierre mensual: corre a diario y actúa solo el último
día del mes) y `MonthlyReviewDeadline` (R6.5, recordatorio del día 15: corre a
diario y actúa solo ese día). El aviso por operador `CredentialNotice` (LV-29)
es **opcional** y queda apagado salvo que se pase `-WithCredentialNotice`.

Horas personalizables, trabajo opcional y desregistro:

```powershell
./scripts/schedule_tasks.ps1 -AlertsAt "06:30" -DigestAt "07:15" -BackupAt "22:00" `
  -ExecutiveReportDay Monday -ExecutiveReportAt "07:30" -MonthlyRecordsAt "23:30" `
  -MonthlyReviewDeadlineAt "08:00"
# Activar además el aviso opcional de vigencias a cada operador (LV-29):
./scripts/schedule_tasks.ps1 -WithCredentialNotice -CredentialNoticeAt "07:30"
# Quitar todas las tareas (incluye las opcionales):
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

El aviso opcional de vigencias al operador (LV-29) se agrega con el mismo patrón
cuando se quiera activar —`mkjob credentials "notify_expiring_credentials"
"*-*-* 07:30:00"`—; solo avisa a operadores con correo en su ficha (los demás se
reportan y se omiten). Acepta `--dry-run` y `--days N` (ventana, 30 por defecto).

El cierre de cumplimiento mensual (LV-30) se agrega con `mkjob monthly
"check_monthly_records" "*-*-* 23:30:00"`: corre a diario y **actúa solo el
último día del mes** (crea las revisiones pendientes y avisa a Dirección). Acepta
`--period YYYY-MM` (mes puntual), `--force` (correr fuera del último día) y
`--dry-run`. La revisión pendiente queda como alerta viva (regla "Cumplimiento
mensual de registros") hasta que Dirección la marca Cumple/No cumple.

El recordatorio del día 15 (R6.5) se agrega con `mkjob monthly-deadline
"check_monthly_review_deadline" "*-*-* 08:00:00"`: corre a diario y **actúa solo
el día 15**, escalando a Dirección en un segundo correo las revisiones del mes
anterior que sigan pendientes. No crea ni cambia revisiones -- solo reporta lo
que `check_monthly_records` ya dejó pendiente. Acepta los mismos flags
(`--period YYYY-MM`, `--force`, `--dry-run`).

El límite de jornada de vuelo (R7.5) se agrega con `mkjob duty-limit
"check_flight_duty_limit" "*-*-* 07:45:00"`. **Reporta el día anterior**, no el
de hoy: una jornada sólo está completa cuando terminó, y correrlo sobre el día
en curso daría un total parcial que se lee como "todo en orden". `--date
YYYY-MM-DD` apunta a un día puntual y `--dry-run` reporta sin enviar. El límite
es `selectors.DAILY_FLIGHT_LIMIT` (8 horas, decidido con el usuario el
2026-08-12). **Cuenta tiempo de vuelo, no jornada real** — el día del piloto
incluye traslados, montaje y espera de ventana meteorológica — así que es un
**piso**: superarlo es con certeza exceso; no superarlo no prueba que la jornada
estuvo dentro del límite.

La verificación de eficacia (R7.6) se agrega con `mkjob alert-effectiveness
"check_alert_effectiveness" "*-*-* 08:30:00"`: corre a diario y escala lo que
lleva **30 días resuelto sin que nadie confirme que la acción sirvió**. El plazo
es `Alert.EFFECTIVENESS_DAYS` (decidido con el usuario el 2026-08-12, alineado
con el ciclo mensual de R6.5); `--days N` lo cambia para una corrida puntual sin
tocar el modelo, y `--dry-run` reporta sin enviar. **Las alertas resueltas antes
de que este campo existiera no vencen nunca** — no hay fecha honesta que
inventarles, y ponerlas todas en "vencidas hoy" habría estrenado la función con
un atraso que nadie causó.

El registro histórico de cumplimiento (R7.7) se agrega con `mkjob snapshot
"snapshot_compliance" "*-*-* 23:00:00"`. **Conviene activarlo cuanto antes**: la
tendencia que exige ISO 9.1.1 solo puede calcularse sobre los días que ya
quedaron guardados, así que cada día que pasa sin este trabajo es un día de
historia que no se puede recuperar después. Acepta `--date YYYY-MM-DD` (para
rellenar un día puntual, aunque **rellenar el pasado guarda los números de hoy**,
no los de ese día — sirve para inicializar, no para reconstruir historia) y
`--dry-run`.

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
