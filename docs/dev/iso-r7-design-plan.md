# Diseño de las cláusulas ISO pendientes (R7.4 – R7.7)

**Fecha:** 2026-08-11
**Alcance:** diseño, no implementación. Es lo que la fila del tablero pide
textualmente (*"solo diseño"* / *"diseñar el resto"*) y lo que decidió el usuario
para todo el bloque `R7`: **"dejar la base y el mapeo, no implementar completo."**
**Mapeo cláusula → dónde vive hoy:** [docs/auditoria-iso-trazabilidad.md](../auditoria-iso-trazabilidad.md)

---

## Para qué sirve este documento

Las 4 filas que quedaban de `R7` no son código pendiente: son **decisiones de
forma pendientes**. Este documento las resuelve hasta donde se puede resolver
sin inventar reglas de negocio, y **nombra explícitamente qué falta preguntar**
en cada una.

Regla que se siguió en las cuatro: **reusar el mecanismo que ya existe antes de
crear uno nuevo.** El proyecto ya tiene motor de alertas, tablero de acciones
correctivas, auditoría *append-only*, trabajos programados y un patrón de
*gate* documental (`RequireDgacPermitPdfMixin`). Casi todo lo que pide la norma
se apoya en algo de eso.

> **Nota de contexto:** este diseño se escribió el mismo día en que cerraron
> R6.1, R6.2, R6.4, R7.1, R7.2, R7.3, R8.1 y R4.7, y **varios de esos cambios
> alteran el punto de partida de estas 4 cláusulas** (se señala en cada una).
> El documento de trazabilidad se actualizó en el mismo commit.

---

## R7.4 — Calidad del entregable (ISO 9001 8.5.1 / 8.6)

**Qué exige:** control de calidad del procesamiento — RMSE contra GCP, GSD
logrado vs. requerido, cobertura y traslapes. Informe de precisión y validación
interna **antes** de liberar al cliente. Criterios de aceptación acordados.

**Estado:** ⬜ brecha completa. Es la más grande de las cuatro, y no por volumen
de código: **introduce un dominio que la app no tiene.** Hoy AeroControl cubre
*el permiso para volar* y *el registro de que se voló*; no cubre *si lo
entregado sirve*.

### Forma propuesta

Un modelo nuevo, `Deliverable` (entregable), que **no guarda el producto** —
las nubes de puntos y ortofotos viven en el pipeline de procesamiento y en `Z:`,
no acá. Guarda **las métricas y la firma de validación**, que es lo que el
auditor pide ver.

| Campo | Por qué |
|---|---|
| `gsd_required_cm` / `gsd_achieved_cm` | La cláusula pide *logrado vs. requerido*, no solo logrado. Dos campos, no uno. |
| `rmse_xy_cm` / `rmse_z_cm` | Horizontal y vertical se aceptan con umbrales distintos; un solo RMSE no permite decidir. |
| `gcp_count` / `checkpoint_count` | Un RMSE calculado sobre los mismos puntos que se usaron para ajustar no es una verificación independiente. Separar GCP de puntos de chequeo es lo que vuelve el número defendible. |
| `coverage_pct` / `overlap_pct` | Lo pide la cláusula explícitamente. |
| `status` | `draft` → `validated` → `released`, más `rejected`. Ver el *gate* abajo. |
| `validated_by` / `validated_at` | "Validación interna antes de liberar" es una firma, no un booleano. Mismo patrón que `MonthlyComplianceReview.reviewed_by/reviewed_at`. |

**Anclaje (decisión de forma, no obvia):** el candidato natural es
`FlightPermission` — en esta app el permiso *es* el trabajo (tiene centro de
costo, propósito, ubicación, fechas, flota y operadores). Pero un entregable
real puede abarcar **varios** vuelos y hasta varios permisos, y un permiso puede
no producir entregable. Por eso: **FK a `CostCenter` (el contrato, siempre
presente) + M2M opcional a `FlightPermission`**, no FK único al permiso.

**Criterios de aceptación: no se tipean por entregable.** Si el umbral lo
escribe una persona en cada fila, no es un criterio acordado, es una opinión por
registro. Van **al contrato**: campos de umbral en `CostCenter`
(`required_gsd_cm`, `max_rmse_xy_cm`, `max_rmse_z_cm`), y el entregable
**compara contra ellos** y calcula el resultado. Así "cumple / no cumple" es
derivado, no declarado — y cambiar el umbral del contrato no reescribe la
historia de los entregables ya validados (para eso el entregable guarda también
el umbral vigente al momento de validar, igual que `purpose_legacy` preserva el
valor original en R3.1).

**El *gate*:** pasar a `released` se bloquea si no cumple los umbrales, salvo
que lleve una excepción documentada y firmada. **Ya existe el precedente exacto
en el código**: `RequireDgacPermitPdfMixin` (R2.4) bloquea aprobar/completar un
permiso sin el PDF de la DGAC. Mismo mixin, misma forma, otro criterio.

### Dónde se cruza

- **R7.6**: un entregable que no cumple **abre una no conformidad** (re-vuelo o
  levantamiento rechazado). Es el disparador más importante de esa cláusula.
- **R7.7**: `gsd_achieved / gsd_required` y la tasa de rechazo son dos de los
  KPI operacionales que 9.1.1 pide y que hoy no existen.

### Qué falta preguntar

1. **Los umbrales reales.** RMSE y GSD aceptables salen del contrato con el
   cliente. No se pueden inventar: un umbral inventado que la operación no
   cumple convierte el *gate* en un estorbo que alguien va a desactivar.
2. **¿Un entregable por permiso, o por faena/mes?** Cambia el anclaje.
3. **¿Quién valida?** Rol nuevo o el grupo `Dirección` que ya revisa el cierre
   mensual.

---

## R7.5 — IPER, baterías LiPo y jornada de vuelo (ISO 45001 6.1.2 / 8.1.2, y 9001 6.1)

**Qué exige:** matriz IPER del trabajo en terreno (caída sobre personas,
intemperie, desplazamientos, fatiga del piloto, incendio de baterías LiPo), con
controles por jerarquía: zonas de exclusión, EPP, almacenamiento seguro de
baterías, **límites de jornada de vuelo**. La cláusula 9001 6.1 pide además
**evaluación de riesgo por vuelo** (SORA o equivalente): pérdida de enlace,
*flyaway*, meteorología, fauna, obstáculos.

**Estado:** ⬜ — pero **con dos partes ya resueltas hoy y una derivable sin
datos nuevos**, así que es mucho menos brecha de lo que dice el tablero.

### Lo que ya dejó de faltar (2026-08-11)

- **Meteorología** (factor de riesgo de 6.1): la resolvió `R8.1`. La ficha del
  plan geo muestra pronóstico de viento y ráfagas para el día del permiso.
- **Baterías LiPo**: existe `registry.Battery` (`R7.2`) con ciclos, salud y
  firmware. Ver la tensión de diseño abajo.

### Lo barato: límite de jornada de vuelo

**Derivable con cero datos nuevos.** `FlightRecord` ya tiene `actual_date`,
`departure_time`, `arrival_time` y `pilot`. Agregar por `(pilot, actual_date)` y
comparar contra un límite da la evidencia completa de esa parte de la cláusula.
Es exactamente la misma forma que `apps.operations.selectors.total_flight_duration`
(R7.1) — un agregado en Python, porque `FlightRecord.duration` es una
`@property`, no una columna.

Único insumo que falta: **el número del límite**, y si es diario, semanal o
ambos. La DGAC o el procedimiento interno lo fijan; no se puede adivinar.

### Tensión de diseño que hay que resolver antes de tocar `Battery`

La gestión de baterías **en desuso** (14001: residuo peligroso) y el
almacenamiento seguro son hechos **de la empresa**, no telemetría: DJI no
reporta "esta batería se dio de baja y se entregó a un gestor de residuos".

Pero `Battery` se diseñó a propósito como **espejo de solo lectura de AeroLink**
(ADR-0002: el inventario de baterías es de AeroLink porque DJI reporta ciclos de
forma nativa). Un campo de baja/disposición sería **el primer campo de esa tabla
que AeroLink no posee**, y rompería la propiedad que la hace fácil de
sincronizar.

Dos salidas, hay que elegir una:

1. **Modelo aparte** (`BatteryDisposal`, FK a `Battery`): conserva el espejo
   puro. Cuesta una tabla más y un *join* para responder "¿está de baja?".
2. **`Battery` deja de ser espejo puro**: se acepta que tenga campos propios y
   se documenta qué columnas manda AeroLink y cuáles no. Más simple de leer,
   pero cada sincronización futura tiene que saber qué no pisar.

**Recomendación: (1).** La regla "ninguno escribe en el dominio del otro" del
ADR-0002 es lo que hace que el contrato con AeroLink sea sostenible; erosionarla
por un campo es barato hoy y caro cuando `X.4` aterrice.

### La matriz IPER en sí

Dos niveles, y conviene no confundirlos:

- **Catálogo permanente** (`Hazard` + `RiskControl`): el IPER estándar del
  levantamiento con RPAS. Se escribe una vez, se revisa anualmente. Es casi un
  documento — y de hecho **podría ser uno** (`company-procedure`, tipo que ya
  existe desde R4.8) si no se necesita consultarlo por campos.
- **Evaluación por trabajo** (`RiskAssessment`, ligada al permiso o al vuelo):
  instancia el catálogo y registra qué controles se aplicaron esta vez.

**Decisión pendiente y no menor:** el *checklist* preoperacional hoy existe como
**documento adjunto** (`rpa-checklist`, LVE-003), no como formulario
estructurado. Estructurarlo daría datos consultables (y KPI para 9.1.1), pero es
reemplazar un flujo de papel que la operación ya usa. **No hacerlo sin pedido
explícito**: es el tipo de cambio que se siente como burocracia nueva si nadie
lo pidió.

---

## R7.6 — No conformidades, re-vuelos y verificación de eficacia (ISO 10.2)

**Qué exige:** registro y **análisis de causa raíz** de re-vuelos,
levantamientos rechazados e incidentes; acciones correctivas **con verificación
de eficacia**; reporte a la autoridad cuando corresponda.

**Estado:** 🟡 — y **hoy avanzó bastante**, así que el "Falta" del documento de
trazabilidad quedó desactualizado y se corrigió.

### Lo que ya dejó de faltar (2026-08-11)

- **"Resolver una alerta no pide motivo ni causa raíz"** → lo cerró `R6.2`:
  resolver a mano ahora **exige** un motivo, y queda en
  `Alert.resolution_reason`. Los llamadores automáticos siguen sin motivo a
  propósito (no hay humano a quien preguntar).
- **"Completar la tarjeta no resuelve la alerta"** (que el documento listaba
  como brecha de evidencia) → lo cerró `R6.1`: el cierre es bidireccional.
- **"Los movimientos no registran quién los hizo"** (brecha de evidencia de
  7.1.3, del mismo tenor) → lo cerró `R5.2`.

### Lo que sigue faltando, y su forma

**1. Verificación de eficacia — reusar el patrón de R6.5, no inventar uno.**

Hoy resolver es terminal: nadie vuelve a preguntar si la acción sirvió. Lo que
la norma pide es una revisión *posterior*. La forma ya está construida en esta
misma casa: `check_monthly_review_deadline` (R6.5) corre a diario, actúa solo un
día y **escala lo que nadie firmó**. Mismo molde:

- `Alert.resolution_reason` ya existe (R6.2) → agregar
  `effectiveness_due_date` y `effectiveness_verified_at/by`.
- Un comando programado escala lo resuelto hace N días **sin verificar**.
- Reabrir sigue siendo posible (`reopen()`), que es la salida natural cuando la
  verificación dice "no sirvió".

Esto es lo más barato y de mayor rendimiento de toda la cláusula.

**2. La no conformidad como registro propio, distinto de una alerta.**

Un re-vuelo o un levantamiento rechazado **no es una alerta de vencimiento**.
Forzarlo al motor de `AlertRule` repetiría el error que ya se evitó en R5.1
(esa rama vigila "vence en N días", no otra cosa). Modelo nuevo,
`NonConformity`:

- `source`: `reflight` / `rejected_deliverable` / `incident` / `audit_finding`.
- `description`, `root_cause`, `corrective_action`.
- Verificación de eficacia (los mismos campos del punto 1 — o mejor, el mismo
  patrón extraído a un *mixin* compartido con `Alert`).
- **GFK al objeto de origen** (`content_type` + `object_id`): el patrón ya está
  usado dos veces en el repo (`Document`, `Alert`), y acá hace falta porque el
  origen puede ser un entregable, una mantención, un vuelo o nada.

**3. Reporte a la DGAC como paso trazado.**

Hoy no hay dónde decir "esto se reportó a la autoridad el día X con folio Y".
Para un incidente que legalmente exige notificación, **eso es justo la evidencia
que el auditor pide**. Es barato: dos campos (`reported_to_dgac_at`,
`dgac_report_reference`) en `NonConformity`.

**4. Simulacros.**

Registro de simulacros: probablemente no necesita modelo — un tipo de documento
más (mismo criterio que R7.3 con calibración) alcanza si lo único que se guarda
es "se hizo, esta fecha, este acta".

### Qué falta preguntar

- ¿Cuántos días para verificar eficacia? (R6.5 usó "el día 15" porque el
  procedimiento interno lo decía; acá no hay número conocido.)
- ¿Qué incidentes exigen reporte a la DGAC? Eso decide si el campo es opcional
  o si hay un *gate* como el de R7.4.

---

## R7.7 — KPIs con meta y acción (ISO 9001 9.1.1)

**Qué exige:** KPI con **meta**, **tendencia** y **acción cuando no se cumple**.
Sugeridos por la guía: precisión lograda vs. requerida, tasa de re-vuelos, horas
de vuelo sin incidentes, disponibilidad de equipos, cumplimiento de plazos.

**Estado:** 🟡. Hay comparación período contra período (`compare_periods`), y
desde `R6.4` se ve también en la web, no solo en el correo. Falta lo que
convierte un número en KPI.

### El problema que R6.4 dejó documentado y esta cláusula tiene que resolver

`R6.4` documentó un hallazgo incómodo: los 3 KPI actuales (`valid_pct`,
`expired`, `due_30`) **se evalúan siempre "a hoy"**, sin importar el período
pedido — `build_compliance_report` / `_cost_center_row` solo miran `start`/`end`
para las estadísticas de resolución. Consecuencia: **comparar período actual
contra anterior da siempre "sin cambio"** en esas 3 filas, por construcción.

Un KPI cuya tendencia estructuralmente no puede moverse no es un KPI. **Ésta es
la parte de la cláusula que hay que arreglar primero**, y tiene solución
concreta y autocontenida:

**`ComplianceSnapshot`** — un trabajo programado (diario o semanal) que escribe
una fila con los totales del día: `date`, `cost_center` (nullable para el
consolidado), `total`, `valid`, `expired`, `due_7/15/30`. La tendencia pasa a
ser una consulta sobre historia real en vez de dos fotos del mismo instante.

Es barato, no toca nada existente (solo agrega), y **desbloquea la tendencia de
todos los KPI que vengan después**. Es la recomendación de por dónde seguir.

### Meta y acción

- **Meta**: un modelo de configuración chico, `KpiTarget` (`metric_code`,
  `target_value`, `direction`, `owner`). Misma naturaleza que `AlertRule`:
  configuración por *tenant*, sin padre único del cual derivar, así que **lleva
  su propio FK a `tenant`** (ADR-0001: solo las raíces cargan *tenant*).
- **Acción cuando no se cumple**: **no inventar un tercer mecanismo.** Ya hay
  dos y funcionan: un KPI incumplido abre una **tarea en el tablero** (el
  mecanismo de acción correctiva que 10.2 ya usa) o una **no conformidad**
  (R7.6) si amerita causa raíz. Reusar es lo que evita tener tres bandejas de
  pendientes que nadie mira completas.

### De qué dependen los KPI operacionales

| KPI que pide la guía | De qué depende | ¿Disponible? |
|---|---|---|
| Precisión lograda vs. requerida | `R7.4` | No |
| Tasa de re-vuelos | `R7.6` | No |
| Horas de vuelo sin incidentes | `R7.1` (hecho) + `R7.6` | Mitad |
| Disponibilidad de equipos | `Aircraft.status` + estados de taller de `R5.1` (hechos) | **Sí** |
| Cumplimiento de plazos | fechas del permiso vs. fechas de vuelo | **Sí, derivable** |

Los dos últimos se pueden calcular **hoy**, sin ningún modelo nuevo.

### Qué falta preguntar

**Las metas.** "95% de documentos vigentes" o "menos de 2% de re-vuelos" son
decisiones de la dirección, no del código. Sin ellas, `KpiTarget` es una tabla
vacía.

---

## Orden recomendado

Criterio: primero lo que no necesita ninguna decisión de negocio y desbloquea al
resto.

1. **`ComplianceSnapshot`** (de R7.7). No necesita preguntar nada, no toca
   código existente, y sin él la tendencia de cualquier KPI es una ilusión.
   **Es por acá donde conviene seguir.**
2. **Verificación de eficacia** (de R7.6). Reusa el molde de R6.5; solo falta un
   número (cuántos días).
3. **Límite de jornada de vuelo** (de R7.5). Cero datos nuevos; solo falta el
   límite.
4. **Los dos KPI ya disponibles** (disponibilidad de equipos, cumplimiento de
   plazos), una vez que exista el *snapshot*.
5. **`NonConformity`** (R7.6) — modelo nuevo, pero de forma clara.
6. **`Deliverable`** (R7.4) — **el de mayor valor de negocio y el más
   bloqueado**: sin los umbrales reales del contrato no se puede cerrar. Vale
   preguntarlos pronto, porque de él dependen dos KPI y el disparador principal
   de las no conformidades.
7. **IPER estructurado** (R7.5) — último, y solo con pedido explícito: es el que
   más se arriesga a sentirse como burocracia nueva.

---

*Relacionado:* [MASTER_PLAN.md](../../MASTER_PLAN.md) bloque `R7`;
[docs/auditoria-iso-trazabilidad.md](../auditoria-iso-trazabilidad.md);
[adr-0002-coexistencia-aerolink.md](adr-0002-coexistencia-aerolink.md)
(por qué `Battery` es espejo y no maestro).
