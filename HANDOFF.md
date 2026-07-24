# HANDOFF — punto de retomada

> Escrito al cerrar la sesión del **2026-07-24**. Léelo primero, en una sesión
> nueva, antes de tocar código. Cuando la situación descrita aquí quede
> resuelta, **borra este archivo**: el estado permanente vive en
> `MASTER_PLAN.md`, no aquí.

## Cómo retomar en un chat nuevo

Pega esto como primer mensaje:

```
Retomo el trabajo de AeroControl. Lee en este orden:
1. HANDOFF.md  (situación puntual y primera tarea)
2. AGENTS.md   (contrato: precedencia documental, DoD, gate)
3. MASTER_PLAN.md (tablero de bloques: qué está hecho y qué sigue)
Luego dime qué recomiendas y sigamos.
```

Con eso el agente reconstruye el contexto sin necesitar el historial del chat
anterior. No hace falta re-explicar la auditoría: está en `AUDIT_CLAUDE.md`.

---

## ⚠️ Lo primero: dos ramas divergieron

Hay **dos líneas de trabajo paralelas** sobre `codex/impeccable-ui-audit`, y
falta unirlas. Nada se perdió; nada se sobrescribió.

| Rama | Qué tiene |
| --- | --- |
| `codex/stabilization-blocks-0-6` (mía, **39 commits**, ya en remoto) | Auditoría + Bloques 0, 1, 2, 4-parcial y 6.1/6.2 completos. 257 tests, cobertura 88% |
| `codex/impeccable-ui-audit` (remoto, **8 commits** que yo no tenía) | Traducciones de permisos de vuelo y asignaciones, filtros de planificación, docs de respaldo, chequeo de calidad de datos, y **el mismo fix del dashboard** |

Ambas parten de `75e56f2`. La otra línea la hizo otra sesión/Codex en paralelo.

### Los 7 archivos que ambos lados tocaron

```
BACKLOG.md
apps/registry/forms.py
apps/registry/tests.py
apps/registry/views.py
locale/es/LC_MESSAGES/django.po
locale/es/LC_MESSAGES/django.mo   <-- binario: NO resolver a mano
templates/dashboard/index.html    <-- ambos arreglamos el MISMO bug (P0)
```

### PRIMERA TAREA: el merge

```bash
git checkout codex/stabilization-blocks-0-6
git merge origin/codex/impeccable-ui-audit
```

Criterios al resolver, en orden de importancia:

1. **`django.mo` — no editar.** Es binario compilado. Resuelve el conflicto
   quedándote con cualquiera de los dos y **recompila**:
   `uv run python scripts/compile_translations.py`. El `.mo` correcto sale del
   `.po` fusionado.
2. **`django.po` — conservar AMBOS conjuntos** de `msgid`. Los dos lados
   añadieron traducciones distintas y todas hacen falta. Ojo: puede haber
   entradas duplicadas tras el merge; `compile_translations.py` avisa.
3. **`templates/dashboard/index.html` — el mismo bug, dos arreglos.** Ambos
   quitamos el `{% block extrahead %}` duplicado. Quédate con **una sola**
   versión que además conserve mis cambios de la paleta de gráficos por tema y
   el listener de `aero:themechange` (si eliges la versión remota, esos se
   pierden). Verifica con `apps/core/test_templates.py`.
4. **`apps/registry/*`** — su trabajo es i18n y filtros; el mío añade
   `CostCenter.responsible_operator` y `verbose_name` con acrónimos. Son
   complementarios: deben quedar los dos.
5. **`BACKLOG.md`** — trivial, quédate con ambas secciones.

Cerrar el merge con el gate completo, que es el criterio de aceptación:

```powershell
pwsh scripts/verify.ps1
```

Debe dar **257 tests o más** en verde y cobertura ≥83%. Si `verify.ps1` pasa
sin ejecutar todos los pasos, algo está mal (ese bug ya se corrigió en `0ed12c5`).

---

## Estado del trabajo (detalle en `MASTER_PLAN.md`)

Ruta de ejecución del plan: **completa en su alcance.**

| Bloque | Estado |
| --- | --- |
| 0 · Higiene | ✅ salvo el tag `v0.1.0-alpha` (TL.11) |
| 1 · Alertas ⇄ Kanban | ✅ backend + UI, revisada en navegador |
| 2 · Notificaciones + `JobRun` | ✅ |
| 4 · Robustez de datos (parcial) | ✅ B4.1 y B4.2 |
| 6.1/6.2 · Reportes | ✅ |
| 5R · Legibilidad y contraste | ✅ salvo R.10 |

**Diferidos por decisión del plan** (no ejecutar sin instrucción explícita):
Bloque 3 (UX Kanban), Bloque 5 (centro de administración — `JobRun` ya está
listo para que lo consuma), Bloque 6.3 (asistente IA), y B4.3/B4.4
(habilitaciones DGAC y compatibilidad operador–aeronave, que además deben
proponerse como **diseño antes de implementar**).

## Pendientes que requieren acción del dueño, no del agente

1. **Operador responsable** en cada centro de costo real: sin él,
   `send_alert_digest` no tiene a quién escribir (avisa y continúa, no falla).
2. **Grupo `Dirección`** con usuarios que tengan correo: es el destinatario por
   defecto de `send_executive_report`.
3. **Duplicados de operadores**: correr `find_duplicate_operators` (solo
   reporta) sobre los datos reales para ver los 4 grupos del backlog antes de
   fusionar nada.
4. **Tag** `v0.1.0-alpha` — decidiste hacerlo tú:
   `git tag -a v0.1.0-alpha -m "Estabilización inicial (PR #9)" main`
5. **Programar los trabajos** en el equipo que corresponda:
   `./scripts/schedule_tasks.ps1 -EnvFile "C:/AeroControl_Data/.env"`

## Deuda conocida que conviene atacar pronto

- **R.10 / T5.1** — `static/css/app.css` tiene **dos generaciones de tokens
  superpuestas**. Ya provocó que un arreglo de contraste hubiera que hacerlo
  dos veces (la regla vieja ganaba por especificidad). Unificarlo hará que cada
  cambio de color deje de ser un juego de adivinanzas.
- **FASE 2 (seguridad)** — los IDOR F-03..F-06 de `AUDIT_CLAUDE.md` siguen
  abiertos. Hoy están mitigados porque `tenant` es `NULL` en todos los
  registros, pero **hay que cerrarlos antes de centralizar el servidor**.
- **FASE 3 · T3.2** — decidir la clave de tenancy. Es barato ahora y caro con
  datos reales acumulados; es el bloqueador de la centralización y de DJI.

## Notas de entorno (no son bugs del repo)

- `ruff format --check` puede devolver código de salida 2 con «Acceso
  denegado» aunque el chequeo real pase. Es un artefacto de permisos de
  `.ruff_cache`/`.pytest_cache` en el equipo donde se trabajó, no del proyecto.
- Para revisar la app sin tocar datos reales: `./scripts/run-demo.ps1`
  (puerto 8010, directorio de datos aislado). Usuario de demo `admin`.
