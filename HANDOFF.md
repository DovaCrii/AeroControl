# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) — específicamente su
> sección **"Prioridades post-v0.4.0-beta"**, al inicio del archivo. Este
> documento es solo el resumen de estado; el historial detallado de cada
> LV-N vive en las filas de `MASTER_PLAN.md` y en `CHANGELOG.md`, no aquí.

## Estado al 2026-08-05

- **Versión**: `v0.4.0-beta` (tag publicado). Cubre todo desde `v0.3.0-alpha`:
  el módulo geoespacial (KMZ/KML) y de seguimiento operativo completos, más
  ~65 hallazgos de una revisión en vivo con datos reales de la DGAC.
- **Deploy**: `p340` confirmado en el commit `8224373` (el último de `main`
  al cerrar esta ventana), servicio activo. Todo lo listado en
  `MASTER_PLAN.md` hasta LV-65/LV-63 está desplegado — **con una excepción
  sin confirmar** (ver "Pendiente inmediato" abajo).
- **Datos reales en producción**: 12 centros de costo, 41 operadores, 15
  aeronaves, con documentos DGAC reales empezando a cargarse (permisos de
  vuelo aprobados, credenciales).

## Pendiente inmediato (antes de dar por cerrado el deploy)

Al desplegar LV-64 se agregó un `DocumentType` nuevo
(`dgac-rpa-operation-authorization`) vía `seed_document_types` — comando
idempotente, pero que **no se re-ejecuta solo** (mismo gotcha que
`init_dgac_board` en LV-45). Se pidió al usuario correrlo en la Parte 2 del
deploy, pero **no llegó a confirmarse explícitamente** que la línea
`Ensured 10 document types (1 created)` haya salido bien. Si una sesión
nueva retoma esto:

```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py seed_document_types
```

Si dice `Ensured 10 document types (0 created)` ya está hecho; si dice
`(1 created)` recién quedó al día. Sin esto, el tipo "Autorización de
Operación RPA (DGAC aprobada)" no aparece en el desplegable y **nadie puede
aprobar un permiso de vuelo nuevo** en producción.

## Cómo desplegar (patrón establecido)

El usuario corre los comandos por su propia sesión SSH a `p340` y pega la
salida; Claude no tiene credenciales de producción ni debe manejarlas.

**Sin sudo:**
```bash
cd /opt/aerocontrol && git pull --ff-only && uv sync --frozen
```

**Con sudo** (el bloque pide la contraseña de sudo del usuario — no
manejarla; ajustar si hay migraciones/seeds nuevos):
```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py migrate --no-input && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

**Verificación:**
```bash
sudo systemctl status aerocontrol --no-pager && git log --oneline -1
```

Verificar visualmente requiere credenciales que Claude no tiene; sí se puede
confirmar que un cambio de CSS/JS llegó pidiendo el archivo estático
directamente (no requiere login), como se hizo para LV-63.

## Antes de tocar código

- Correr **`ruff check .` y `ruff format --check .`**, no solo `pytest` — el
  CI de GitHub (`ci.yml:26-27`) corre ambos y en esta ventana estuvo en rojo
  varios días sin que nadie lo notara (ver higiene 2026-08-05 en
  `MASTER_PLAN.md`).
- Recompilar el `.mo` después de tocar el `.po` (`polib`, la VM no tiene
  `gettext`) — ver hazard ya anotado en la memoria del repo.
- Ver `MASTER_PLAN.md` → "Prioridades post-v0.4.0-beta" para el orden
  vigente de lo que sigue (el ensayo de restauración de respaldos es lo más
  crítico ahora mismo, no un ítem de código).
