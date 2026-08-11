# HANDOFF — AeroControl

> Punto de retome entre ventanas/sesiones. La **fuente de verdad del trabajo
> pendiente** es [MASTER_PLAN.md](MASTER_PLAN.md) — sección **"Prioridades
> post-auditoría"**, al inicio del archivo. Este documento es solo el resumen
> de estado; el detalle de cada ítem vive en las filas de `MASTER_PLAN.md`.

## 🔒 CIERRE DE VENTANA — 2026-08-11, tercer tramo (R8.1, X.3, R7.2 — se agotó lo implementable sin decisiones nuevas)

**Empezar aquí.** Tras cerrar el BLOQUE R6 y los ítems sueltos (ver la sección
siguiente, del mismo día), el usuario pidió "avanzar hasta terminar todos los
pendientes". Se cerraron los tres que quedaban implementables. **Con esto se
agotó el trabajo que se puede hacer sin una decisión nueva del usuario o sin
que AeroLink exista.**

```
... (cadena de los dos tramos anteriores) ...
    └─ codex/r4-company-documents-repository        R4.6
        └─ codex/r4-remaining-document-types           R4.8
            └─ codex/r5-qualifications-on-ficha            R5.8
                └─ codex/r8-weather-forecast                  R8.1
                    └─ codex/x3-padron-readonly-api              X.3
                        └─ codex/r7-battery-inventory               R7.2  ← HEAD
```

- **R8.1 — clima/viento.** Las 4 preocupaciones que la fila nombraba (CSP,
  secretos, caché, degradación) las resolvió **una sola decisión: la llamada se
  hace del lado del servidor, nunca desde el navegador.** El CSP **no cambió**
  (verificado leyendo el header y confirmando cero peticiones del navegador a
  Open-Meteo); **no hay secretos** porque se eligió Open-Meteo justamente por no
  pedir API key, a diferencia de UAV Forecast/OpenWeather; se cachean también
  los fallos (si no, un proveedor caído costaría una petición por vista); y todo
  camino de falla devuelve `None` y la tarjeta no aparece. **Apagado por
  defecto** (`WEATHER_ENABLED=False`), así un despliegue que no lo active
  conserva la propiedad de cero llamadas salientes. Sin dependencia nueva
  (`urllib` de la stdlib; `requests` está solo en el árbol de dev). Aterriza en
  la ficha del plan geo (ahí están las coordenadas, vía `bbox_*`), para el día
  del `valid_from` del permiso, no "hoy". **Bandit encontró un agujero real**
  (B310: `urlopen` acepta `file://`, así que un `WEATHER_API_URL` mal escrito
  habría sido una lectura de archivo local) — se validó el esquema en vez de
  silenciar el warning, con 5 tests que ejercitan el guard.
- **X.3 — padrón de solo lectura para AeroLink.** `GET /api/v1/registry/aircraft/`
  con `?serial=` (la búsqueda que AeroLink de verdad hace). **Solo lectura de
  verdad**: no hay ruta de escritura, un superusuario recibe `405` — no se puede
  aflojar después repartiendo un permiso. Serial exacto, nunca parcial (un
  prefijo atribuiría telemetría a la aeronave equivocada). Campos mínimos: las
  fechas de seguro/pesos/VLOS **no se exponen**. Acotado por tenant y
  `view_aircraft`, verificado **en ambos sentidos**. Contrato completo en el
  ADR-0002 sección 4.
- **R7.2 — inventario de baterías.** Alcance confirmado con el usuario antes de
  migrar (crear el espejo ahora, sin carga manual). `registry.Battery` +
  migración `0030` + lista de solo lectura. **Es un espejo, no el maestro**: el
  ADR-0002 le da el inventario a AeroLink porque DJI reporta ciclos nativamente.
  **Queda vacío a propósito** hasta `X.4`, y el estado vacío lo explica en
  pantalla para que no se lea como un bug. `source`/`synced_at` registran
  procedencia y frescura, porque un conteo en 0 sin fecha es ambiguo (¿batería
  nueva, o sincronización que nunca corrió?).

### Qué queda, y por qué no se puede avanzar solo

Ninguno de estos está bloqueado por falta de trabajo técnico:

- **X.4** (recibir sesiones de vuelo de AeroLink) y **X.5** (identidad Entra ID
  vs Django) — **dependen de que AeroLink exista**. Hoy está en M0 (andamiaje).
  X.3 y R7.2 ya dejaron el lado de AeroControl listo para ambos.
- **R7.4/R7.5/R7.6/R7.7** — el encabezado del BLOQUE R7 dice, por decisión del
  usuario, *"dejar la base y el mapeo, no implementar completo"*, y esas 4 filas
  dicen **"solo diseño"**. Ese entregable de diseño **es**
  `docs/auditoria-iso-trazabilidad.md`, que existe y se actualizó hoy. Quedaron
  en ⬜ a propósito: marcarlas ✅ es una decisión del usuario sobre si el mapeo
  ya cuenta como cerrado, no algo que corresponda decidir sola.
- **R4.1a/R4.4** — esperan al usuario (renombrar 2 carpetas en `Z:`) y a que
  alguien configure un antivirus real para los `.msg`. `--apply` sigue sin
  correrse nunca.
- **R5.9** (Kanban para taller) — aparcado por decisión explícita del usuario.
- **T1.x/T3.5/T4.x/T5.8** — deuda técnica, diferida por la política del propio
  tablero (punto 8 de "Prioridades": incremental, sin migración grande).

### Cabos sueltos concretos para la próxima ventana

1. **25 commits en 25 ramas locales apiladas, nada pusheado ni mergeado.** Es
   el pendiente más grande y es una decisión del usuario. Conviene una sesión
   dedicada solo a eso.
2. **El AOC real: lo sube el usuario a mano, y NO necesita el deploy.**
   Compartió `OneDrive\...\Certificado AOC 1485.pdf` y confirmó que lo que
   importa es tenerlo "visible y a mano". No se importó desde acá: la base local
   de `.env` está vacía y la operación real vive en `p340`.
   **Corrección de una afirmación equivocada de esta misma sesión**: se dijo
   primero que estaba bloqueado esperando el deploy. **No lo está.** Las dos
   piezas necesarias ya están en `main` desde el 2026-08-03 (`7897dcb`,
   LV-27/28), o sea ya desplegadas: `/compliance/company-documents/` y
   `/compliance/documenttype/new/`. El tipo `aoc-certificate` es **solo una fila
   en la base, no código**, así que se crea desde la app:
   - `/compliance/documenttype/new/` → Nombre `Certificado AOC`, Código
     **`aoc-certificate`** (exacto), "Vence" **desmarcado** (decisión del
     usuario: es único e interno, no se renueva), "Seguro" desmarcado.
     Pide permiso `compliance.add_documenttype`.
   - `/compliance/company-documents/` → "+ Cargar documento" → el PDF.
     Pide `compliance.add_document`.
   **Por qué el código exacto importa**: `seed_document_types` usa
   `get_or_create(code=...)`, así que cuando se despliegue encontrará esa fila y
   la dejará intacta — no duplica ni sobrescribe el nombre. El usuario eligió
   hacerlo él mismo en el navegador (2026-08-11) en vez de que se hiciera por
   SSH, para ver exactamente qué se sube y dónde queda.
3. **Al desplegar a `p340`**: `uv sync` (dependencia nueva `reportlab`),
   `seed_document_types` a mano (gotcha LV-45/LV-64; pasa de 10 a 17 tipos, y
   respeta el `aoc-certificate` que el usuario haya creado a mano antes —
   ver punto 2), migración `registry/0030` (tabla `Battery`, nueva, sin tocar
   datos existentes), y decidir si se activa `WEATHER_ENABLED`.
4. **`.claude/launch.json` (ignorado por git) quedó con `WEATHER_ENABLED=True`**
   para poder revisar el clima en el demo. Si molesta, quitarlo.

---

## 🔒 CIERRE DE VENTANA — 2026-08-11, primeros dos tramos (R6.2 verificado, BLOQUE R6 completo, R4.7/R7.3/X.2 + 3 checkboxes de R1 corregidos)

**Empezar aquí en la próxima ventana.** Esta ventana retomó exactamente donde
quedó la anterior (mismo working tree, misma pila de ramas) en dos tramos:
primero cerró el cabo suelto que quedaba (R6.2 en el navegador) y el resto del
BLOQUE R6 (R6.3-R6.5); después, con permiso de seguir cerrando bloques, avanzó
sobre ítems sueltos de R7/X/R4 y **encontró y corrigió 3 checkboxes de R1 que
llevaban desactualizados desde el 2026-08-07** (ya estaban resueltos en el
código, nadie los había marcado). **BLOQUE R6 completo (R6.1–R6.5) y BLOQUE
R1 completo (R1.1–R1.5), los 10 ✅.**

### Lo que se hizo (7 commits nuevos, apilados sobre `codex/r6-alert-resolve-with-reason`, ninguno mergeado ni pusheado)

```
... (cadena completa de la ventana anterior, sin tocar) ...
    └─ codex/r6-alert-resolve-with-reason          R6.2  (ya existía)
        └─ codex/r6-group-same-origin-alerts           R6.3
            └─ codex/r6-executive-report-web-pdf            R6.4
                └─ codex/r6-monthly-review-deadline             R6.5
                    └─ codex/r7-x2-calibration-cert                 X.2 (checkbox) + R7.3
                        └─ codex/r4-operator-credential-pdf-flag        R4.7
                            └─ codex/r1-stale-checkbox-fix                R1.1/R1.2/R1.3 (checkboxes)  ← HEAD
```

- **R6.2 verificado en el navegador.** El único punto pendiente de la ventana
  anterior. Contra el demo real: el modal abre con el textarea "Motivo / causa
  raíz", `required` bloquea el envío vacío, el POST con motivo devuelve 204 y
  la fila pasa a "Reabrir" (contador de 17→16), `reopen()` la devuelve a su
  estado original. Sin sorpresas — ya queda cerrado del todo.
- **R6.3 — agrupar alertas del mismo origen.** `_group_alerts` (views.py)
  agrupa alertas **sin resolver** por `(alert_rule_id, watched_date)` — p. ej.
  una póliza de seguro de flota que vence en una fecha y cubre varias
  aeronaves, o un lote de habilitaciones DGAC vencidas el mismo día. Solo
  afecta la lista (no la paginación ni el queryset): cada alerta sigue
  resolviéndose (y cerrando su propia tarea Kanban) de forma independiente.
  Cada fila agrupada conserva la acción de tarea de cada miembro + un botón
  nuevo "Resolver (N)" (`AlertResolveGroup`) que reutiliza `AlertResolveForm`
  para pedir un motivo compartido — sin eso, cerrar un grupo de 4 significaba
  escribir el mismo motivo 4 veces. Verificado en vivo: 3 grupos reales
  aparecieron solos con los datos del demo, resolver un grupo lo separó en
  filas "Resuelta" individuales, y reabrir una por una reformó los grupos
  hasta volver al estado original (17 alertas).
- **R6.4 — informe ejecutivo en la web + PDF.** La premisa del plan ("hoy solo
  existe como correo") estaba desactualizada — `ComplianceReportView` ya
  existía con CSV/XLSX/DOCX. Lo que de verdad faltaba era la comparación
  contra el período anterior que el correo (`send_executive_report`) sí
  mostraba; se movió a `reports.py` (`compare_periods`/`previous_period`/
  `COMPARED_KPIS`) para que la web y el correo lean la misma función en vez de
  dos copias — el propio docstring del módulo ya prometía eso y no era cierto
  para esta tabla. **Hallazgo documentado, no corregido**: los 3 KPIs de
  documentos/vigencias (`valid_pct`, `expired`, `due_30`) se evalúan siempre
  "a hoy" — comparar período actual vs. anterior da **siempre "sin cambio"**
  en esas 3 filas por construcción (ya pasaba en el correo, ahora es visible
  también en la web); arreglarlo de verdad exigiría una tabla de snapshots
  históricos que no existe. Solo la fila de alertas resueltas varía de
  verdad. Exportación **PDF** nueva (`ComplianceReportPdfView`, `reportlab`,
  dependencia nueva sin paquete de sistema que instalar en la VM). Verificado
  en vivo: tabla de comparación traducida con el patrón "+0" esperado,
  descarga de PDF confirmada por `fetch` (magic bytes `%PDF-1.4`).
- **R6.5 — recordatorio del día 15.** Alcance confirmado con el usuario antes
  de implementar (pregunta explícita en el chat): es un **recordatorio de
  pendientes**, no una segunda revisión formal. Comando nuevo
  `check_monthly_review_deadline` — corre a diario, actúa solo el día 15,
  escala a Dirección en un segundo correo las `MonthlyComplianceReview` del
  mes anterior que sigan `pending`. **Nunca crea ni cambia una revisión** —
  `check_monthly_records` (LV-30) sigue siendo el único dueño; así un fallo
  del cierre de fin de mes se ve como 0 filas aquí, no como un falso "todo en
  orden". Registrado en `scripts/schedule_tasks.ps1` y `docs/scheduled-
  operations.md`. Verificado manualmente el correo contra el backend de
  consola (asunto/cuerpo en español, singular/plural, período interpolado)
  antes de confiar solo en los tests automatizados.

### Gotcha que se repitió 3 veces esta ventana: `makemessages` fuzzy

Cada uno de R6.3/R6.4/R6.5 agregó strings nuevos al `.po` y **cada corrida de
`makemessages` fuzzy-matcheó algo mal** (11 entradas fuzzy en total, en 4
rondas) — exactamente el hazard ya documentado en la memoria del repo. Todas
se revisaron a mano (`grep fuzzy`), se corrigieron y se recompiló el `.mo` con
`polib` antes de seguir. Un caso interesante en R6.4: reusar el msgid ya
existente `"Current"` para una columna nueva ("valor de este período") habría
sido un falso amigo con su significado real en la app ("versión vigente del
documento") — se detectó y se renombró antes de traducir, no después.

### Decisión de negocio tomada en vivo con el usuario hoy

- **R6.5**: se preguntó explícitamente qué debía hacer el chequeo del día 15
  (recordatorio de pendientes vs. segunda revisión formal independiente vs.
  otra cosa) antes de implementar, porque un procedimiento que alimenta una
  auditoría ISO no es algo para adivinar. El usuario eligió la opción
  recomendada (recordatorio).

### Segundo tramo de hoy: X.2, R7.3, R4.7, y 3 checkboxes de R1

- **X.2** — declarar por escrito quién es maestro de qué entre AeroControl y
  AeroLink. **Checkbox desactualizado**: ya estaba resuelto por completo desde
  el 2026-08-07 en `docs/dev/adr-0002-coexistencia-aerolink.md` (sección 3).
  Solo se corrigió el tablero.
- **R7.3** (ISO 7.1.5, calibración) — `calibration-certificate` agregado a
  `seed_document_types` (`requires_expiry=True`). Alcance acotado al tipo de
  documento, tal como lo pedía la fila del tablero; el modelo de GCP que
  menciona la brecha ISO queda fuera (sin pedido concreto).
- **R4.7** (licencia RPA del operador) — `OperatorList` gana
  `has_credential_pdf` (subquery `Exists` sobre `Document`); la lista de
  operadores muestra "Sin PDF" cuando la vigencia DGAC no tiene el documento
  real en archivo, tenga fecha puesta o no. Verificado en vivo: los 9
  operadores del demo muestran "Sin PDF" (ninguno tiene el `Document` real
  cargado hoy).
- **R1.1/R1.2/R1.3 — checkboxes corregidos, no había código pendiente.**
  Las tres ya estaban resueltas desde el commit `ee3db03` del 2026-08-07 (el
  mismo commit que cerró R1.4/R1.5, que sí se habían marcado) — el calendario
  ya no oculta las vigencias DGAC/JAC en su vista por defecto, un permiso sin
  folio ya no renderiza `"None"`, y el panel de vencimientos ya distingue
  urgencia por color con "Vence en N días". **Re-verificado en vivo hoy antes
  de tocar el tablero** (no solo confiando en el mensaje del commit): el
  feed `/calendar/events/?types=all` trae `RPA-2002 · Seguro JAC` y las
  credenciales DGAC de Bruno Díaz/Elena Vega; el panel de vencimientos
  muestra `text-warning-emphasis fw-semibold` y enlaza a
  `#upcoming-expirations`. **BLOQUE R1 queda completo (R1.1–R1.5).**

### Lección de esta ventana: el tablero puede mentir en cualquier dirección

Ya se sabía que un ⬜ puede estar hecho de verdad (memoria
`aerocontrol-repo-hazards`, caso T2.1). Hoy se confirmó **tres veces más en
el mismo bloque** (R1.1/R1.2/R1.3), todas desde el mismo commit de hace 4
días. **Antes de implementar cualquier fila marcada ⬜/🔄, grep el código real
primero** — puede ahorrar toda la implementación.

### Qué preguntar/decidir en la próxima ventana, en orden de urgencia

1. **¿Mergear/pushear algo de la pila?** Son ahora 18 commits en 18 ramas
   locales apiladas (11 de la ventana anterior + 7 de hoy), nada se subió
   todavía. El usuario decide cuándo y cómo.
2. **BLOQUE R1 y BLOQUE R6 completos.** No queda nada abierto en ninguno de
   los dos. Lo que sigue en el tablero (2026-08-11, fin de esta ventana) son
   todos ítems que necesitan una decisión del usuario antes de implementar,
   no trabajo que se pueda seguir de forma autónoma:
   - **R7.2** (modelo de baterías/ciclos) — "diseñar la forma" ligado a
     AeroLink; el contrato real todavía no está construido (`X.3`).
   - **X.3** (endpoint de solo lectura del padrón para AeroLink) — superficie
     nueva expuesta a otro sistema; el ADR ya define el contrato pero no la
     forma exacta de la respuesta.
   - **R8.1** (clima/viento) — decisión de arquitectura (primera llamada HTTP
     saliente del proyecto: CSP, secretos, caché, degradación).
   - **R5.8** (¿la sección Habilitaciones sigue siendo de primer nivel en el
     sidebar o se integra a la ficha del operador?) y **R5.9** (Kanban para
     mantención, aparcado) — ambos esperando que el usuario decida.
   - **R4.6** (Documentos de la empresa como repositorio real) — no está
     bloqueado, simplemente no se empezó; candidato razonable si se quiere
     seguir sin esperar una decisión, pero es un ítem más grande (categorías,
     filtros, búsqueda) que merece confirmarse antes de arrancar.
3. **Higiene**: `reportlab` es una dependencia nueva (`pyproject.toml`/
   `uv.lock`) — si se despliega a la VM Ubuntu, correr `uv sync` allá también.
   `seed_document_types` pasó de 13 a 14 tipos (`calibration-certificate`) —
   correr a mano en `p340` cuando se despliegue (mismo gotcha LV-45/LV-64 de
   siempre).

---

## 🔒 CIERRE DE VENTANA — 2026-08-10, sesión larga (X.1 → R6.2)

**Empezar aquí en la próxima ventana.** Esta sección resume TODA la sesión
de hoy (las entradas fechadas 2026-08-10 más abajo son el detalle
cronológico de cada ítem, quedan como bitácora). `MASTER_PLAN.md` ya tiene
cada fila marcada ✅ con su propio resumen técnico — esto es la vista de
conjunto para retomar sin haber visto la conversación.

### Lo que se hizo (11 commits, ninguno en `main`, ninguno pusheado)

Pila completa de ramas locales, cada una apilada sobre la anterior (la
última es donde quedó el working tree):

```
main
 └─ codex/serial-number-normalize          X.1 (2 commits)
     └─ codex/r4-document-repository-schema        R4.2
         └─ codex/r4-document-repository-import    R4.1/R4.3/R4.5
             └─ codex/r5-movement-attribution-and-log   R5.2/R5.3
                 └─ codex/r5-aircraft-fiche-expediente      R5.4/R7.1
                     └─ codex/r5-jac-insurance-filing-status    R5.7 + fix migración 0028
                         └─ codex/r5-aircraft-selector-and-bulk-assign  R5.5/R5.6
                             └─ codex/r5-maintenance-workshop-flow          R5.1
                                 └─ codex/r6-alert-task-bidirectional-close     R6.1
                                     └─ codex/r6-alert-resolve-with-reason          R6.2  ← HEAD
```

**`main` no se tocó.** Nada de esto se mergeó ni se pusheó — el usuario no lo
pidió y el trabajo de merge/push/despliegue queda para cuando él decida.
Si la próxima sesión no tiene el mismo working tree (por ejemplo, corre en
un checkout nuevo de `main`), **este trabajo completo no estará ahí** —
hay que ir a buscar estas ramas.

**Bloques cerrados hoy:**

- **X.1** — `Aircraft.serial_number` normalizado (espacios) + `unique=True`.
  Las 2 discrepancias de caracteres (`RPA-4647`, `RPA-4884`) las confirmó
  el usuario contra el registro físico: el valor de la app ya era el
  correcto en ambos casos, no se tocó la base. **El usuario corrige 2
  nombres de carpeta en `Z:` por su cuenta** (pendiente de su lado, no
  del código).
- **BLOQUE R4** (parcial) — importador `import_document_repository`
  (modo informe + `--apply`) para el repositorio de `Z:`. **R4.1a**: 14/16
  aeronaves calzan hoy; las 2 de arriba calzarán solas en cuanto el usuario
  renombre esas 2 carpetas. **R4.4**: el gate de antivirus para `.msg`
  (15 archivos reales) sigue bloqueado porque `DOCUMENTS_ANTIVIRUS_COMMAND`
  sigue vacío en todos los ambientes — nadie ha configurado un ClamAV real
  todavía. **`--apply` nunca se corrió** — ni contra la copia local ni
  contra producción; sigue pendiente esa decisión del usuario. **R4.6/R4.7/
  R4.8(resto)** sin empezar (documentos de la empresa, licencia RPA
  incompleta, tipos de documento que faltan).
- **BLOQUE R5 — completo** salvo dos ítems dejados fuera a propósito:
  R5.8 (observación "Habilitaciones parece redundante", capturada, el
  usuario no ha dicho si la revisa) y R5.9 (idea de usar Kanban para
  visualizar el flujo de taller, aparcada — el propio usuario dudó si hacía
  falta). R5.1-R5.7 y R7.1 todos hechos y verificados en vivo contra el
  demo.
- **BLOQUE R6 — arrancado, 2 de 5 hechos.** R6.1 (bug del cierre
  bidireccional alerta↔tarjeta) y R6.2 (resolver con motivo, ISO 10.2).
  **R6.3/R6.4/R6.5 sin empezar**: agrupar alertas del mismo origen, informe
  ejecutivo en la web + PDF, revisión del día 15.

### Lo único sin verificación visual: R6.2

Todo lo anterior se probó en vivo contra el demo (`aerocontrol-demo`,
`D:\I+D\AeroControl\scripts\run-demo.ps1`, login `demo`/`demo-review-only`).
**R6.2 no** — la herramienta de preview del navegador tuvo un problema
técnico justo al cierre de la ventana (el panel no montaba, los `ref_N` no
resolvían). Queda cubierto por 36 tests que ejercitan el modal
(GET renderiza el formulario, POST inválido devuelve 422, POST válido
resuelve y guarda el motivo, HTMX devuelve 204 + `modal-form-success`,
`reopen()` limpia el motivo) pero **nadie lo miró en un navegador de
verdad**. Antes de considerar este ítem realmente cerrado, abrir
`/compliance/alert/` en el demo, hacer clic en "Resolver" en una alerta sin
resolver, y confirmar que el modal se ve bien y el flujo completo funciona.

### Hallazgos no anticipados por el plan (quedaron documentados en su fila
de `MASTER_PLAN.md`, resumen aquí para no perderlos)

- **Bug real en la migración `0028`** (de X.1): el orden de sus 2
  operaciones rompía con datos que tuvieran aeronaves con `serial_number`
  en blanco de verdad — silencioso contra la copia de restauración (no
  tenía ninguna), reventó contra el demo (tiene 6). Corregido, commit
  separado (`e5dea67`). **Lección**: cuando una migración de datos solo se
  prueba contra una copia "limpia", correrla también contra el demo (u
  otro set con casos límite) antes de darla por cerrada.
- **Dos formas reales del repositorio `Z:` que el plan no anticipaba**:
  una subcarpeta con su propia subcarpeta anidada, y un archivo suelto en
  la raíz de una carpeta de aeronave. Ambas las encontró el importador real
  corriendo contra `Z:` de verdad (no contra datos sintéticos) — arregladas
  con test de regresión antes de seguir.
- **Bug de atribución no listado originalmente en R5.2**: editar la
  ubicación de una aeronave por el formulario normal tampoco atribuía
  autor al movimiento — mismo mecanismo que el bug de asignaciones que sí
  estaba en el plan.
- **Carrera de señales en R6.1**: la primera versión (con `pre_save`, igual
  que las demás señales de la ventana) perdía la escritura de
  `Alert.resolve()` contra el guardado original todavía pendiente — la
  atrapó un test que fallaba, se corrigió pasando a `post_save`.

### Decisiones de negocio/diseño tomadas en vivo con el usuario hoy

- **R5.1**: dos caminos desde "pending" (corto in-situ, largo por taller);
  filas existentes en `in_progress` se dejan tal cual, se editan a mano si
  hace falta; alerta de permanencia como bandera visual simple, no como
  `Alert`/`AlertRule` formal — decisión explícita de no sobre-complejizar.
- **Kanban para seguimiento de mantención (R5.9)**: aparcado, evaluar más
  adelante si la bandera visual no alcanza.
- **X.1**: los 2 valores en disputa (`RPA-4647` ceros, `RPA-4884` `1581`)
  son los que ya tenía la app — confirmado contra el registro físico, no
  adivinado.

### Qué preguntar/decidir en la próxima ventana, en orden de urgencia

1. **Verificar R6.2 en el navegador** (ver arriba) antes de considerarlo
   realmente terminado.
2. **¿Mergear/pushear algo de esta pila?** Nada se subió todavía; son 11
   commits en 11 ramas locales. El usuario decide cuándo y cómo.
3. **BLOQUE R6 restante**: R6.3 (agrupar alertas), R6.4 (informe ejecutivo
   web + PDF), R6.5 (revisión día 15) — orden sugerido por `MASTER_PLAN.md`,
   ninguno bloqueado.
4. **R4**: falta que el usuario corrija 2 carpetas en `Z:` y que alguien
   configure un antivirus real antes de que R4.1a/R4.4 puedan cerrarse del
   todo; recién ahí tiene sentido correr `--apply`.
5. **R5.8/R5.9**: quedan esperando que el usuario decida si los revisa.

## Estado al 2026-08-10 (última actualización: R6.1 hecho)

- **✅ R6.1 (bug) hecho — arrancó el BLOQUE R6.** Cierre bidireccional
  alerta↔tarjeta: antes solo funcionaba "resolver la alerta mueve la
  tarjeta"; ahora "completar la tarjeta (arrastrarla a una etapa
  `status_type=completed`) también resuelve la alerta" —
  `apps/workboard/signals.py`, nuevo. **Detalle técnico no obvio**: tuvo
  que ser `post_save`, no `pre_save` (que es el patrón que usan las demás
  señales de esta ventana, registry/maintenance) — `Alert.resolve()`
  vuelve a guardar la tarjeta si no quedó en la etapa "canónica" (la
  primera `completed` por `order`), y con `pre_save` esa segunda escritura
  se pisaba con el guardado original todavía pendiente. Se detectó con un
  test que fallaba, no a ojo. Verificado con la vista real de
  drag-and-drop (`task-move`), no solo con `.save()` directo.
- Rama `codex/r6-alert-task-bidirectional-close`, apilada sobre toda la
  cadena de esta ventana, sin mergear ni con push.

## Estado al 2026-08-10 (R5.1 hecho, BLOQUE R5 cerrado)

- **✅ R5.1 hecho — propuesta de diseño discutida en vivo con el usuario antes
  de implementar** (dos preguntas de diseño resueltas en el chat: caminos
  corto/largo desde "pending", y alcance de la alerta de permanencia).
  `MaintenanceRecord` tiene ahora dos caminos: el corto original
  (`in_progress → completed`, mantenimiento in-situ) y uno largo nuevo
  (`sent → at_workshop → finished → in_transit → completed`, para lo que
  sale a un taller externo). Una señal nueva
  (`apps/maintenance/signals.py`) liga esto al historial del equipo:
  mueve `Aircraft.current_location`/`status` a "mantenimiento" al entrar
  en `sent` y de vuelta a "casa matriz"/"activo" al completar desde
  `in_transit`, reusando la señal de OPS-3 que ya generaba
  `ResourceMovementLog` — el rastro del activo queda automático, sin
  código nuevo para eso. La "alerta de permanencia" que el usuario pidió
  quedó como **bandera visual** (`status_changed_at` + ⚠ en la lista +
  texto en la ficha), **no** como `Alert`/`AlertRule` formal — decisión
  explícita para no sobre-complejizar (conectarlo al motor genérico de
  alertas habría exigido que esa rama soportara "lleva N días" además de
  "vence en N días", afectando `FlightPermission`/`MonthlyComplianceReview`
  de paso). La idea de usar Kanban para visualizar esto quedó **aparcada**
  (R5.9) — el propio usuario no está seguro de que haga falta.
  Verificado en vivo contra el demo: cadena completa de botones, aeronave
  marcada correctamente en cada paso, movimiento registrado, datos de
  prueba limpiados después.
- **BLOQUE R5 queda completo** salvo R5.8 (observación de Habilitaciones,
  capturada, esperando que el usuario decida) y R5.9 (idea de Kanban,
  aparcada a propósito). Siguiente foco pedido por el usuario: **BLOQUE R6**
  (alertas y reportes).
- Rama `codex/r5-maintenance-workshop-flow`, apilada sobre toda la cadena
  de esta ventana, sin mergear ni con push.

## Estado al 2026-08-10 (R5.5/R5.6 hechos)

- **✅ R5.5 y R5.6 hechos, BLOQUE R5 queda casi completo.** `Aircraft.
  selector_label` ("RPA-1 · M300 · S/N 1ABC234") enlazado vía
  `label_from_instance` en los 6 selectores de aeronave de toda la app
  (`registry`, `operations`, `maintenance`) — deliberadamente separado de
  `__str__` (que sigue siendo solo la matrícula). `bulk_assign_aircraft` +
  `AircraftBulkAssignForm` + vista `AircraftBulkAssign` toman el "+ Nuevo"
  de `aircraftassignment-create`, mismo movimiento que `OperatorBulkAssign`
  ya hacía. Verificado en vivo contra el demo (selector con etiquetas
  correctas, formulario de asignación múltiple renderizando y traducido).
  Del **BLOQUE R5 solo queda R5.1** (mantenimiento con flujo real — pide
  propuesta de diseño primero, no es un cambio chico como los demás) y
  **R5.8** (observación de Habilitaciones, ya capturada sin implementar,
  esperando que el usuario decida si la revisa ahora o después).
- Rama `codex/r5-aircraft-selector-and-bulk-assign`, apilada sobre toda la
  cadena de esta ventana, sin mergear ni con push.

## Estado al 2026-08-10 (R5.7 hecho + fix de migración)

- **✅ R5.7 hecho.** `Aircraft.insurance_status` (`pending`/`active`) rastrea
  el trámite del seguro JAC antes de que exista la fecha real de vigencia
  — mismo patrón que `CostCenter.contract_status`. `clean()` fuerza
  `"active"` en cuanto llega un `insurance_expiry` real, así el campo no
  puede quedar obsoleto diciendo "en trámite" después de que la póliza ya
  se recibió. Columna "Seguro" de la lista de Aeronaves ahora distingue 3
  estados: `—` / **"En trámite"** / fecha vigente-atrasada.
- **🐛 Bug real encontrado y corregido, no en el trabajo de hoy sino en
  X.1 (migración `0028`, ya comiteada en una rama anterior de esta misma
  ventana).** Verificando R5.7 en vivo contra el **demo** (no la copia de
  restauración) la migración `0028` falló con `IntegrityError`: el demo
  tiene 6 aeronaves con `serial_number=""` de verdad, y la copia de
  restauración usada para probar X.1 no tenía ninguna, así que el bug
  quedó silencioso ahí. La causa: el orden de las 2 operaciones de esa
  migración intentaba poner `NULL` en una columna que todavía era
  `NOT NULL` en ese punto. Corregido a 3 pasos (nullable → limpiar datos →
  `unique=True`) directamente en `apps/registry/migrations/
  0028_aircraft_serial_number_unique.py`. **Lección para la próxima
  ventana**: cuando una migración de datos toca una copia de restauración
  como único banco de pruebas, correrla también contra el demo (u otro
  set con casos límite reales) antes de darla por cerrada — los datos
  "limpios" de producción no cubren todos los casos.
- Rama `codex/r5-jac-insurance-filing-status`, apilada sobre toda la
  cadena de esta ventana (X.1 → R4 schema → R4 import → R5.2/R5.3 →
  R5.4 → R5.7), sin mergear ni con push.

## Estado al 2026-08-10 (R5.4/R7.1 hechos)

- **✅ R5.4 y R7.1 hechos en el mismo cambio.** La ficha de aeronave ya tenía
  documentos y movimientos (OPS-6); se agregó historial de mantenciones
  **completadas** (separado de las abiertas de LV-26, que ya tenían su propia
  tabla con botones — así no se repite el mismo registro dos veces) y horas
  de vuelo acumuladas (`apps/operations/selectors.py`,
  `total_flight_duration` + `format_duration` — esta última también la usa
  ahora `FlightRecord.duration_display`, que antes duplicaba la misma lógica
  de formato). El agregado de horas de vuelo es exactamente lo que R7.1
  (ISO 7.1.3) pedía por separado — un solo lugar de implementación sirve a
  los dos ítems del tablero. Verificado en vivo contra el demo con datos de
  prueba descartables (un `MaintenanceRecord` completado y un `FlightRecord`
  de 1h30, creados y borrados en la misma sesión — el demo queda como
  estaba). Rama `codex/r5-aircraft-fiche-expediente`, apilada sobre las
  de R5.2/R5.3 y R4, sin mergear.

## Estado al 2026-08-10 (R5.2/R5.3 hechos)

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
