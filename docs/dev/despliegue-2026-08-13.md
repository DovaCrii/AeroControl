# Despliegue del 2026-08-13 — secuencia lista para ejecutar

Nota interna (`docs/dev/`, no autoritativa). Es la Parte D del runbook
(`ubuntu-vm-deploy.md`) **concretada para esta tanda**, para no tener que
reconstruirla mientras se despliega. Se borra cuando la tanda esté aplicada.

## Qué entra

20 commits: `R8.4` (clima en el panel) y el bloque `LV-78` a `LV-91`.

**7 migraciones. Dos tocan datos:**

| Migración | Datos | Qué hace |
|---|---|---|
| `registry/0033` | no | coordenadas de faena en el centro de costo |
| `registry/0034` | **sí** | 4 estados del seguro + `InsuranceHistory`; pone en `missing` las aeronaves que dicen `active` **sin ninguna fecha** |
| `maintenance/0008` | **sí** | `sequence` en el historial + numera las filas existentes por orden de creación |
| `maintenance/0009` | no | borra `changed_at` (columna duplicada) |
| `operations/0017` | no | agrega el estado `expired` al permiso |
| `compliance/0018` | no | nombres de modelo traducibles |
| `operations/0018` | no | idem |

**Un trabajo programado nuevo**: `expire_permissions` (05:30, **antes** de
`generate_alerts`). Quedarían **11 timers**.

**No** hace falta `bootstrap_roles`: no hay permisos nuevos. Las transiciones del
seguro usan `change_aircraft`, que ya existe.

**No** correr `init_dgac_board` — se sacó del runbook (`LV-78`).

## Secuencia

**1. Push (en Windows, `D:\I+D\AeroControl`).** Las ramas sólo existen acá.

```bash
git fetch && git log HEAD..origin/main --oneline && git push origin main
```

Si `git log` imprime algo, **parar**: alguien más empujó. Nunca `push --force`.

**2. Entrar a la VM.** El nombre DNS no resuelve bien; usar la IP de Tailscale.

```bash
ssh levdigital01@100.121.16.118
```

**3. Cargar el entorno.** `set -a` no es opcional: sin él `manage.py` cae a
`config.settings.dev` y muere con `SECRET_KEY not found`.

```bash
cd /opt/aerocontrol && git pull
set -a; source <(sudo cat /etc/aerocontrol.env); set +a
echo "settings=$DJANGO_SETTINGS_MODULE  db=$DB_PATH"   # debe decir prod
```

**4. Respaldo Y verificación, antes de migrar.** No es ceremonia: dos de las
siete migraciones reescriben filas.

```bash
uv run python manage.py backup
uv run python manage.py verify_backup <ruta-que-imprimió-el-anterior>
```

**5. Ver qué va a cambiar `registry/0034`, antes de aplicarlo.** Estas son las
filas que pasarán de "Vigente" a "Faltante": deberían ser `RPA-2019`, `RPA-3696`
y `RPA-7126` (las tres del pendiente `LV-74`). `values_list`, nunca `.all()` —
el código nuevo sobre la base vieja haría `SELECT *` de columnas que aún no
existen.

```bash
uv run python manage.py shell -c "from apps.registry.models import Aircraft; print(list(Aircraft.objects.filter(insurance_expiry__isnull=True).values_list('registration','insurance_status')))"
```

**6. Migrar y publicar estáticos.** `collectstatic` es obligatorio: en prod los
estáticos llevan hash de contenido, y sin `staticfiles.json` toda etiqueta
`{% static %}` falla.

```bash
uv run python manage.py migrate --no-input
uv run python manage.py collectstatic --no-input
sudo systemctl restart aerocontrol
```

**7. El trabajo nuevo, en seco primero.** En producción es probable que cierre
varios permisos de una vez; conviene ver cuántos antes de habilitar el timer.

```bash
uv run python manage.py expire_permissions --dry-run
```

**8. Instalar el timer.** Pegar **entero** el bloque `mkjob` de
`docs/scheduled-operations.md` (es autocontenido y ya incluye `expire`), y
después:

```bash
systemctl list-timers 'aerocontrol-*' --no-pager   # deben ser 11
```

## Comprobaciones después de desplegar

**Lo que no se ve solo.** La tarjeta de clima del panel **sólo aparece** si hay
un permiso vigente con coordenadas o un centro de costo con coordenadas de
faena. En `p340` probablemente no haya ninguno todavía, así que su ausencia se
lee como un despliegue fallido — igual que pasó con `WEATHER_ENABLED`. Cargar
una faena para verla.

**Si alguna regla todavía crea tarjetas Kanban** (`LV-78`), el trabajo diario lo
dirá en su salida; para saberlo antes:

```bash
uv run python manage.py shell -c "from apps.compliance.models import AlertRule; print(list(AlertRule.objects.filter(create_kanban_task=True).values_list('name', flat=True)))"
```

**Y lo que sigue pendiente del lado del usuario, que este despliegue no
resuelve**: cargar las 10 vigencias (`LV-74`), `CSP_REPORT_ONLY=False`,
`DOCUMENTS_ANTIVIRUS_COMMAND`, y los 2 nombres de carpeta en `Z:` (`R4.1a`).
