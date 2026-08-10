# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) — sección **"Prioridades
> post-auditoría"**, al inicio del archivo. Este documento es solo el resumen
> de estado; el detalle de cada ítem vive en las filas de `MASTER_PLAN.md`.

## Estado al 2026-08-10 (última actualización: R5.2/R5.3 hechos)

- **✅ R5.2 (bug) y R5.3 hechos.** `RegistryCreate`/`RegistryUpdate.form_valid()`
  atribuyen el usuario a `_changed_by_user` antes de guardar — cierra el hueco
  en `AircraftAssignment` (crear/editar) y `OperatorAssignment` (editar), y de
  paso uno no listado en el plan original: editar la ubicación de una
  `Aircraft` tampoco atribuía autor (mismo mecanismo, `track_aircraft_location`
  OPS-3). `ResourceMovementLogList` ahora tiene columna `detail`, búsqueda
  (por texto libre **y** por matrícula/nombre del recurso, ya que
  `resource_id` es un UUID sin FK — se resuelve primero qué aeronaves/
  operadores calzan), exportación CSV y scoping por tenant con el mismo truco
  de resolución previa (no hay `tenant_path` posible sin FK). Tests nuevos en
  `test_ops_assignments.py`, `test_ops3_aircraft_location.py` y
  `apps/core/test_tenancy.py` (el archivo donde ya vivían las otras pruebas
  de aislamiento por tenant del padrón).
- Rama `codex/r5-movement-attribution-and-log`, apilada sobre la de R4
  (`codex/r4-document-repository-import`), sin mergear.

## Estado al 2026-08-10 (R4.1/R4.2/R4.3/R4.5 hechos)

- **✅ R4.1/R4.2/R4.3/R4.5 hechos, R4.1a/R4.4 parciales** (bloque
  repositorio documental, `Z:`). Importador `import_document_repository`
  (`apps/compliance/management/commands/`) — informa por defecto, `--apply`
  crea `Document` idempotentemente, se niega si quedan filas bloqueantes.
  Lógica pura en `apps/compliance/repository_import.py`. **Corrido en modo
  informe contra `Z:` real** (copia descartable de la restauración, ya
  borrada): de 73 archivos, 42 `OK`, 15 `REVIEW-NEEDS-ANTIVIRUS`, 5
  `REVIEW-NO-MATCH`, 5 `REVIEW-SENSITIVE`, 5 `SKIP-FORMAT`, 1
  `REVIEW-UNKNOWN-SUBFOLDER` — cuadra exacto con el conteo real. **No se
  corrió `--apply`** — sin escribir nada en ninguna base todavía.
- **Dos hallazgos reales no anticipados por el plan, encontrados corriendo
  contra `Z:` real** (no contra datos sintéticos): (a) una subcarpeta
  (`02.- Solicitud de Vuelos`) tiene a su vez una subcarpeta propia
  (`Junio-Agosto/`) que el primer intento del recorrido **perdía en
  silencio** (sin filesystem/DB de por medio no se detecta este tipo de
  bug — hay que correr contra la estructura real); (b) un archivo suelto en
  la raíz de una carpeta de aeronave, fuera de las 5 subcarpetas fijas.
  Ambos arreglados y con test de regresión antes de seguir.
- **R4.1a**: X.1 (ver abajo) resolvió las 2 discrepancias de espacio; de 16
  aeronaves, **14 ya calzan** por serial. Quedan 2 (`RPA-4647`, `RPA-4884`)
  sin calzar porque el nombre de carpeta en `Z:` **todavía no se corrigió** —
  el usuario dijo que lo hace él mismo en el disco Z, pendiente de su lado.
- **R4.4**: antivirus sigue sin configurarse en ningún ambiente
  (`DOCUMENTS_ANTIVIRUS_COMMAND` vacío) — los 15 `.msg` puros quedan
  bloqueados hasta que exista uno. El gate de antivirus reutiliza
  `scan_uploaded_file` (mismo que el formulario web) vía un adaptador de
  ruta a archivo; probado con un antivirus simulado (mock) en ambos
  sentidos, no contra un ClamAV real.
- **Decisión de diseño propuesta, no validada con el usuario todavía**:
  mapeo de las 5 subcarpetas fijas a `DocumentType` — 2 ya existían
  (`aircraft-registration` para "01.-", `liability-insurance` para "05.-");
  se agregaron 3 nuevos códigos a `seed_document_types` (`flight-request`
  "02.-", `incident-investigation-record` "03.-", `maintenance-certificate`
  "04.-", adelantados desde R4.8 porque el importador no podía clasificar
  esas subcarpetas sin ellos). **Correr `seed_document_types` de nuevo en
  cualquier ambiente donde se vaya a usar el importador** (pasa de 10 a 13
  tipos) — mismo gotcha de despliegue que ya documentaba LV-45/LV-64.
- **`DOCUMENTOS BASES` queda fuera de alcance a propósito** (R4.6, sin
  empezar): el importador de R4.1 no camina esa carpeta.
- 158 tests nuevos entre R4 y X.1 desde la última marca; gate completo
  corrido al cierre de esta ventana (ver más abajo el resultado).

## Estado al 2026-08-10 (X.1 cerrado)

- **✅ X.1 — `Aircraft.serial_number` como llave de cruce, cerrado hoy.**
  `Aircraft.save()` limpia todo el whitespace (incluido el interno —
  `"".join(serial.split())`) — migración `0027` aplicó lo mismo a las 16
  filas reales, resolviendo las 2 discrepancias de espacio (`RPA-4401`,
  `RPA-4436`). Las otras 2 (`RPA-4647` ceros vs "OO", `RPA-4884` `1581` vs
  `1582` contra la carpeta `CC717`) **las confirmó el usuario contra el
  registro físico**: el valor que ya tenía la app era el correcto en ambos
  casos — no se tocó la base. El usuario corrige el nombre de carpeta en
  `Z:` por su cuenta; este repo no escribe ahí. Campo ahora
  `null=True, unique=True` (migración `0028`, mismo patrón que
  `FlightPermission.permission_number`). **X.1 ya no bloquea nada de R4.**
  736 tests verdes (730 antes de esta ventana), `ruff`/`bandit`/`pip-audit`
  limpios. Rama `codex/serial-number-normalize`, sin mergear.
- **Observación en vivo capturada, sin implementar:** el usuario ve
  "Habilitaciones" (`qualification-list`) como redundante con Operadores.
  No es redundancia técnica (`Qualification` alimenta alertas de vencimiento
  y el aviso de compatibilidad B4.4) sino de contenido — la ficha de
  Operador ya muestra `authorizations` (texto libre) y Habilitaciones
  muestra lo mismo estructurado pero casi siempre sin fecha. Capturado como
  **R5.8** en `MASTER_PLAN.md`: no borrar el modelo, evaluar si debe salir
  del sidebar de primer nivel (mismo movimiento que LV-7 hizo con Kanban).
  Propuesta de diseño antes de implementar — el usuario todavía no confirmó
  si prefiere revisarlo ya o mantener el orden vigente (R4 primero).

## Estado al 2026-08-10

- **Desplegado y confirmado en `p340`, commit `e008748`.** Las cinco
  migraciones pendientes (`workboard/0009`, `registry/0024`,
  `operations/0012`, `operations/0013`, `registry/0025`) se aplicaron sin
  error, `collectstatic` corrió y `aerocontrol.service` está
  `active (running)`. Este commit incluye todo lo subido el 2026-08-07:
  B3.1/B3.2/B3.5, T5.7, **BLOQUE R1** completo (3 bugs corregidos + 2
  investigados-no-reproducibles), **R2.1/R2.4/R2.5/R2.6** y **BLOQUE R3**
  completo salvo lo bloqueado en datos reales (R3.1/R3.1a) — R3.2
  (ordenamiento de listas) y R3.3 completo (operador archivado visible,
  `CostCenter.contract_status`, `Aircraft.retired` verificado).
- **709 tests verdes** (686 antes de R2.5; sumaron los de
  R2.5/R2.1/R2.4/R2.6/R3.2/R3.3). `ruff check .` y `ruff format --check .`
  también verdes.
- **Tres documentos de plan nuevos** (solo lectura, sin código):
  `docs/auditoria-iso-trazabilidad.md` (mapeo de las 14 cláusulas ISO),
  `docs/dev/adr-0002-coexistencia-aerolink.md` (contrato con la segunda app,
  AeroLink).
- **AeroLink (repo separado) quedó estabilizado en esta misma ventana**: los
  tres PRs pendientes (#29 esquema+sondas, #30→#33 verificador de
  conectividad/licencia DJI, #31 revisión de plan + ADR-0002) están
  mergeados a `main`, CI verde, 18/18 tests. AL-101 y AL-102 cerrados en el
  tracker. **AL-003 confirmado con evidencia**: ni 443 ni 8883 responden
  desde afuera de la red Tailscale de `p340` — Tailscale Funnel no abre
  puertos, túnela saliente. Decisión tomada: **relay MQTT externo**. Hay un
  worker (cliente MQTT saliente) armado y con tests en la rama local
  `codex/relay-worker` de AeroLink, sin subir — AeroLink quedó aparcado, no
  es el foco de esta ventana.
- **✅ Ensayo de restauración de respaldos — hecho 2026-08-10, primera vez
  que se prueba de verdad.** `aero_ops_20260809_180019.sqlite3` verificado
  (checksum) y restaurado a una ruta de ensayo: 16 aeronaves, 41 operadores,
  14 centros de costo, 2 permisos de vuelo, todo legible por el ORM.
  Registro en `docs/backend-follow-up.md`. La copia restaurada queda en
  `D:\I+D\AeroOpsDesk_Data\restore-drill\aero_ops_drill.sqlite3` (datos
  reales de la DGAC — no debe quedar viva más de lo necesario).
- **✅ R2.2/R2.3 — folio interno correlativo, hecho 2026-08-10.**
  `internal_folio` (`JEJ-2026-NNN`) asignado en `save()` bajo
  `select_for_update()`; backfill probado primero contra la copia restaurada
  (`JEJ-2026-001`/`JEJ-2026-002`) antes de tocar el modelo en serio. `__str__`
  ahora devuelve el folio interno — cascada automática a lista, calendario,
  panel de vencimientos, ficha de CC y plan geo. Verificado en vivo contra
  el demo (folio interno siempre presente, "En proceso" cuando falta el
  folio DGAC).
- **✅ R3.1/R3.1a — vocabulario cerrado de `purpose`, hecho 2026-08-10.**
  `report_purpose_mapping` (solo lectura) corrido contra la copia restaurada:
  solo 3 filas reales con `purpose` en toda la base, las 3 mezclando más de
  un concepto. **Confirmado con el usuario**: los 2 procedimientos SIGO son
  "Fotogrametría" y "Videos" (no "Videografía"). Las 3 filas reales
  quedaron en "Otro" con el texto original preservado. Encontrado y resuelto
  de paso: `Meta.constraints` en una clase abstracta **no se hereda** si la
  subclase concreta declara su propio `Meta` sin subclasificar el del padre
  — cada constraint quedó declarada en el modelo concreto.
- **✅ R2.7 — búsqueda de permisos, hecho 2026-08-10** (ya destrabado por
  R3.1). `search_fields` ahora sí busca por folio interno, folio DGAC,
  `purpose_detail` y ubicación, como ya prometía el placeholder.
- **730 tests verdes** (686 antes de R2.5). `ruff check .`/
  `ruff format --check .` verdes. Catálogo `.po` regenerado dos veces más
  (R2.2/R2.3, R3.1): aparecieron fuzzy nuevos ambas veces, corregidos a
  mano antes de compilar.
- **Todo el BLOQUE R2 y R3 quedó completo esta ventana** — no queda nada
  bloqueado en ese frente. Sigo desatendido con **R4** (repositorio
  documental), el único bloque post-auditoría que falta.

## Pendiente inmediato (antes de dar por cerrado el deploy)

Heredado de sesiones previas, **sigue sin confirmarse**:

```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py seed_document_types
```

Si dice `Ensured 10 document types (0 created)` ya está hecho; si dice
`(1 created)` recién quedó al día. Sin esto, "Autorización de Operación RPA
(DGAC aprobada)" no aparece en el desplegable y nadie puede aprobar un
permiso nuevo. **Ojo — el catálogo pasó de 10 a 13 tipos con R4.1/R4.8**
(`flight-request`, `incident-investigation-record`,
`maintenance-certificate`, agregados 2026-08-10): la próxima vez que se
corra este comando en `p340` el mensaje esperado ya no es "10", es
`Ensured 13 document types (3 created)` la primera vez que se corra después
de este despliegue.

## Dónde retomar el trabajo de código

`MASTER_PLAN.md` → "Prioridades post-auditoría" tiene el orden completo.
**R1, R2, R3 y X.1 están completos. R4.1/R4.2/R4.3/R4.5 también** (hechos
2026-08-10). Pedido explícito del usuario 2026-08-10: **seguir con los
bloques siguientes antes de pensar en desplegar** — acumular más cambios
locales primero, no ir a producción todavía. Lo que queda:

- **Cerrar R4 del todo** (bajo prioridad frente a lo de abajo, no bloquea
  nada): R4.1a espera que el usuario corrija 2 nombres de carpeta en `Z:`
  (`RPA-4647`, `RPA-4884`); R4.4 espera que exista un antivirus configurado
  en algún ambiente; R4.6/R4.7/R4.8(resto) sin empezar.
- **R5-R8** (salvo R5.7/R5.8, ya en el tablero) y el resto de **BLOQUE X**
  (X.2-X.5, contrato AeroLink) — sin empezar, ver el detalle en
  `MASTER_PLAN.md`. **Siguiente foco de esta ventana.**

Decisión de negocio tomada 2026-08-07 para R3.3(b): "contrato cerrado" es un
**eje nuevo e independiente** de `is_active` — un CC con contrato cerrado
sigue en la lista normal (no se archiva), atenuado y agrupado después de
los operativos; `is_active` sigue siendo solo para archivar por
error/duplicado. Decisión tomada 2026-08-10 para R3.1: los 2 procedimientos
SIGO son "Fotogrametría" y "Videos" (no "Videografía").

Ver las filas correspondientes en `MASTER_PLAN.md` para el detalle de cada
fix, incluidos dos bugs reales encontrados y reproducidos en vivo que no
estaban en el plan original (el botón "Volver" de permisos/mantención/
vuelos necesitaba dos clics tras cualquier acción; `PermissionHistory`
mostraba estados en inglés crudo).

## Cómo desplegar (patrón establecido)

El usuario corre los comandos por su propia sesión SSH a `p340` y pega la
salida; Claude no tiene credenciales de producción ni debe manejarlas.

**Sin sudo:**
```bash
cd /opt/aerocontrol && git pull --ff-only && uv sync --frozen
```

**Con sudo** (pide la contraseña de sudo del usuario — no manejarla):
```bash
cd /opt/aerocontrol && set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && uv run python manage.py migrate --no-input && uv run python manage.py collectstatic --no-input && sudo systemctl restart aerocontrol
```

**Verificación:**
```bash
sudo systemctl status aerocontrol --no-pager && git log --oneline -1
```

## Antes de tocar código

- Correr **`ruff check .` y `ruff format --check .`**, no solo `pytest` — el
  CI de GitHub (`ci.yml:26-27`) corre ambos.
- Tras editar el `.po`: revisar entradas `#, fuzzy` (gettext las genera al
  hacer `makemessages` y pueden traer una traducción incorrecta de otro
  string) antes de recompilar con `scripts/compile_translations.py`.
- Ver `MASTER_PLAN.md` → "Prioridades post-auditoría" para el orden vigente.
