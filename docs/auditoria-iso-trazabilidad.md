# Trazabilidad de la auditoría ISO en AeroControl

**Fecha:** 2026-08-07 · **Última actualización:** 2026-08-11
**Fuente:** `09_Levantamientos_Drones_RPAS_Tips_Auditoria.docx` — guía de auditoría
interna para levantamientos digitales con RPAS contra ISO 9001:2015, ISO 14001:2015 e
ISO 45001:2018, con foco en el cumplimiento de la normativa DGAC.

> **Actualización 2026-08-11.** Este documento se escribió el 2026-08-07 y varias de
> sus brechas se cerraron después. **Las 4 cosas que listaba como "hay que arreglar
> antes de que llegue el auditor" están hechas.** El diseño de las 4 cláusulas que
> quedaban solo como planteamiento vive ahora en
> [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md).

## Para qué sirve este documento

Responde una pregunta concreta: **cuando el auditor pida la evidencia de la cláusula X,
¿dónde está en AeroControl?** Y cuando no esté, decir con precisión qué falta y dónde
va a vivir cuando exista.

Decisión del usuario sobre el alcance: *"dejarlo como planteamiento futuro y cómo
distribuirlo en lo que hoy tenemos, pero es importante dar la base de lo que se
solicita"*. Este documento **es** esa base. No todo está implementado; lo que no lo
está queda con su destino nombrado.

**Leyenda:** ✅ cubierto · 🟡 parcial · ⬜ brecha

---

## Mapeo cláusula por cláusula

### 4.2 — Partes interesadas

**Se exige:** matriz de partes interesadas que incluya a la DGAC y a terceros
sobrevolados; gestión de permisos de acceso y avisos a la comunidad.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | El permiso de vuelo modela a la DGAC como contraparte (estados, folio, documentos). Los centros de costo tienen administrador de contrato y contacto responsable. |
| Falta | Terceros sobrevolados y avisos a la comunidad no se modelan. Se relaciona con `R2.6` (poblado/no poblado): un vuelo sobre área poblada es justamente el que necesita ese registro. |

### 6.1 — Riesgos y oportunidades de la operación

**Se exige:** evaluación de riesgo operacional por vuelo (SORA o equivalente): pérdida
de enlace, *flyaway*, meteorología, fauna, obstáculos. Matriz con controles y evaluación
de eficacia.

| | |
|---|---|
| Estado | ⬜ |
| Hoy | **La parte meteorológica está cubierta** (`R8.1`, 2026-08-11): pronóstico de viento, ráfagas y lluvia sobre el área del plan, para el día del permiso. |
| Falta | No hay evaluación de riesgo por vuelo (pérdida de enlace, *flyaway*, fauna, obstáculos). Destino natural: un registro ligado a `FlightRecord` o al permiso. Diseño en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md) (`R7.5`). **El pronóstico se consulta pero no se persiste**: si el auditor pide evidencia de que la revisión meteorológica se hizo para un vuelo concreto, eso todavía no queda registrado. |

### 6.1.3 / 9.1.2 — Cumplimiento legal DGAC

**Se exige:** registro del RPAS en la DGAC; credencial de piloto vigente (válida 36
meses); autorización de operación; certificado de operador (AOC) cuando aplique; seguro
de responsabilidad civil. Aplicación de DAN 151 (áreas pobladas), DAN 91 (reglas del
aire) y DAN 137 (trabajos aéreos especializados).

| | |
|---|---|
| Estado | ✅ **La cláusula mejor cubierta.** |
| Hoy | Registro del RPAS: tipo de documento `aircraft-registration`. Credencial del piloto: `Operator.credential_expiry` + tipo `dgac-credential`, con alerta de vencimiento. Autorización de operación: `dgac-rpa-operation-authorization` — y **aprobar un permiso está bloqueado sin ese PDF firmado** (LV-64). Seguro: `Aircraft.insurance_expiry` + `liability-insurance`, con alerta. Todo con vencimientos vigilados, resumen diario por correo y calendario. |
| Falta | El **AOC de la empresa** existe en papel (`Z:\DOCUMENTOS BASES\DOCUMENTO EMPRESAS`, y el PDF real en OneDrive). **El lugar donde vive ya está construido** (`R4.6`/`R4.8`: repositorio con búsqueda y categoría, tipo `aoc-certificate`); falta que alguien lo suba — no requiere despliegue. La distinción **DAN 151 vs DAN 91** no se registra → `R2.6`. ~~Exigir el PDF oficial también para *completado*~~ hecho (`R2.4`). |
| ~~Riesgo abierto~~ | ~~El calendario no muestra las vigencias DGAC/JAC en su vista por defecto~~ **Resuelto** (`R1.1`): la lista de tipos la deriva el servidor desde `CALENDAR_EVENT_PERMISSIONS`, así que no puede volver a desincronizarse. Verificado en vivo: el feed con `types=all` trae el seguro JAC y las credenciales DGAC. |

### 6.1.3 — Zonas restringidas y privacidad

**Se exige:** consulta de zonas restringidas antes de cada vuelo; prohibición de
sobrevuelo de instalaciones militares, policiales y carcelarias (Art. 82 Código
Aeronáutico). Gestión de imágenes conforme a la Ley 19.628.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | El módulo geoespacial (KMZ/KML) permite cargar y versionar el área de vuelo, y vincularla al permiso. |
| Falta | No hay verificación automática contra zonas restringidas ni registro de que la consulta se hizo. La Ley 19.628 no se aborda: **atención**, el repositorio documental contiene hoy cédulas de identidad y comprobantes bancarios (ver `R4.5`), lo que la vuelve una preocupación inmediata y no teórica. |

### 7.1.3 — Gestión y trazabilidad de equipos

**Se exige:** inventario de RPAS y sensores; **bitácora de mantenimiento y horas de
vuelo por aeronave**; control de ciclos y estado de baterías LiPo; registro de firmware.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | Inventario completo (16 aeronaves con matrícula, modelo, fabricante, serie, centro de costo, estado y ubicación). Historial de mantenciones. Trazabilidad de movimientos entre faenas (`ResourceMovementLog`, *append-only*). |
| Falta | ~~**Horas de vuelo por aeronave**~~ hecho (`R7.1`, 2026-08-10), se muestra en la ficha. **Ciclos de batería y firmware (`R7.2`, 2026-08-11): el modelo existe** (`registry.Battery`: serial como llave de cruce, ciclos, salud, firmware, y `source`/`synced_at` para saber de dónde vino el dato y qué tan fresco es), con lista de solo lectura en Padrón → Baterías. **Pero está vacío**: es un espejo de AeroLink y ese enlace (`X.4`) todavía no existe, así que hoy la cláusula tiene la forma pero no los datos. |
| Nota | Este es el punto donde **AeroLink** cambia el juego: DJI reporta ciclos de batería y horas de forma nativa, sin depender de que el operador los anote. Ver `docs/dev/adr-0002-coexistencia-aerolink.md`. |
| ~~Brecha de evidencia~~ | ~~`ResourceMovementLog.changed_by_user` queda vacío en casi todos los registros~~ **Resuelto** (`R5.2`, 2026-08-10): las vistas CRUD del padrón atribuyen autor, incluido un caso que el plan no listaba (editar la ubicación de una aeronave). Los registros *anteriores* al arreglo siguen sin autor — es historia, no se puede reconstruir. |

### 7.1.5 — Equipos de medición bajo control

**Se exige:** calibración/verificación de sensores, GNSS/RTK y cámaras; puntos de
control terrestre (GCP) y de chequeo; certificados de calibración vigentes.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | **Tipo de documento `calibration-certificate`** (`R7.3`, 2026-08-11), con `requires_expiry=True` porque la cláusula pide un certificado *vigente* — así entra al motor de alertas como cualquier otra vigencia. El `Certificado Calibración.pdf` real de `Z:\CC706-…\04.- Mantenciones` ya tiene dónde clasificarse. |
| Falta | **El modelo de GCP y puntos de chequeo** no existe. Se cruza con `R7.4`: el RMSE solo es defendible si los puntos de chequeo son independientes de los GCP usados para ajustar. Ver [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md). |

### 7.2 — Competencia del personal

**Se exige:** credencial DGAC vigente; registros de formación y experiencia; competencia
del equipo de procesamiento. **Verificar que quien vuela es efectivamente el acreditado.**

| | |
|---|---|
| Estado | 🟡 |
| Hoy | Credencial con vigencia y alerta. Habilitaciones por operador con compatibilidad operador–aeronave (B4.4): al crear un permiso, la app **avisa** si un operador no tiene habilitación que cubra la aeronave asignada. `FlightRecord.pilot` deja registro de quién voló. |
| Falta | ~~El PDF de la licencia no siempre está cargado y no hay señal de cuándo falta~~ **Resuelto** (`R4.7`, 2026-08-11): la lista de operadores muestra una insignia **"Sin PDF"** cuando la vigencia DGAC no tiene el documento en archivo — hoy la marcan los 9 operadores del demo, que es exactamente la brecha que describía. Las habilitaciones ahora se ven en la ficha del operador (`R5.8`). Sigue faltando: la advertencia de habilitación es no bloqueante — decidir si debe serlo; formación y experiencia más allá de la credencial no se modelan. |

### 8.1 — Planificación y control de cada operación

**Se exige:** plan de vuelo y de misión; checklist preoperacional; revisión de
meteorología (viento, visibilidad); evaluación del sitio y obstáculos; altura, VLOS y
zona de despegue. Bitácora de cada vuelo.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | Plan de misión: módulo geoespacial con versionado. Bitácora: `FlightRecord` + tipos de registro operacional (`flight-log`, `rpa-checklist`, `drone-inspection`) con cierre mensual que cruza vuelos contra registros. `Aircraft.vlos` existe como campo. **Meteorología (R8.1, hecho 2026-08-11):** la ficha del plan geo muestra viento máximo, ráfagas, precipitación y probabilidad de lluvia sobre el área del plan para el día en que empieza el permiso vinculado (Open-Meteo, sin API key, llamada del lado del servidor, apagada por defecto vía `WEATHER_ENABLED`). |
| Falta | Evaluación de sitio y obstáculos no se modela. El checklist existe como *documento adjunto*, no como formulario estructurado. El pronóstico es **de referencia y no queda registrado**: si el auditor pide evidencia de que la revisión meteorológica *se hizo* para un vuelo concreto, eso todavía no se guarda (hoy se consulta en vivo, no se persiste con el `FlightRecord`). |

### 8.4 — Control de proveedores y pilotos externos

**Se exige:** acreditación DGAC del proveedor/piloto externo; seguro vigente; requisitos
por contrato; evaluación de desempeño.

| | |
|---|---|
| Estado | ⬜ |
| Falta | No hay concepto de piloto o proveedor externo: todo operador es del padrón interno. Si se subcontrata, hoy no hay dónde registrarlo. |

### 8.5.1 / 8.6 — Calidad del entregable

**Se exige:** control de calidad del procesamiento — RMSE contra GCP, GSD logrado vs
requerido, cobertura y traslapes. Informe de precisión y validación interna antes de
liberar al cliente. Criterios de aceptación acordados.

| | |
|---|---|
| Estado | ⬜ |
| Falta | La app cubre el *permiso para volar* y el *registro de que se voló*, no la **calidad de lo entregado**. Es la brecha conceptualmente más grande: cierra el ciclo entre "voló legalmente" y "el producto sirve". **Diseño listo** (`R7.4`, 2026-08-11) en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md): modelo `Deliverable` que guarda **las métricas y la firma**, no el producto; umbrales de aceptación **en el contrato** (`CostCenter`), no tipeados por entregable; y un *gate* de liberación con el mismo patrón que `RequireDgacPermitPdfMixin` ya usa para el PDF de la DGAC. **Bloqueado por una decisión de negocio**: los umbrales reales de RMSE y GSD salen del contrato con el cliente, no se pueden inventar. |

### 14001 6.1.2 / 8.1 — Aspectos ambientales

**Se exige:** gestión de residuos peligrosos (baterías de litio); perturbación de fauna
y ruido en áreas sensibles.

| | |
|---|---|
| Estado | ⬜ |
| Falta | No se modela. **La base para la gestión de baterías ya existe** (`registry.Battery`, `R7.2`), pero hay una tensión de diseño que resolver antes de tocarla: la baja de una batería es un hecho **de la empresa**, y `Battery` se diseñó como espejo de solo lectura de AeroLink (ADR-0002). Sería el primer campo que AeroLink no posee. Las dos salidas (modelo aparte vs. dejar de ser espejo puro) están evaluadas en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md). Fauna y ruido se cruzan con la evaluación de riesgo de 6.1. |

### 45001 6.1.2 / 8.1.2 — Peligros de SST

**Se exige:** matriz IPER del trabajo en terreno (caída sobre personas, intemperie,
desplazamientos, fatiga del piloto, incendio de baterías LiPo). Controles según
jerarquía: zonas de exclusión, EPP, almacenamiento seguro de baterías, **límites de
jornada de vuelo**.

| | |
|---|---|
| Estado | ⬜ |
| Falta | La matriz IPER no se modela. **Diseño listo** (`R7.5`, 2026-08-11) en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md), y la cláusula está **menos vacía de lo que decía**: la meteorología la cubre `R8.1` y las baterías tienen modelo (`R7.2`). El **límite de jornada de vuelo** es derivable de `FlightRecord` (fecha, hora de salida y llegada, piloto) **sin datos nuevos** — mismo agregado que `total_flight_duration` de `R7.1`; solo falta el número del límite (diario/semanal), que lo fija la DGAC o el procedimiento interno. **Advertencia del diseño**: estructurar el *checklist* preoperacional (hoy documento adjunto) no debería hacerse sin pedido explícito — reemplaza un flujo de papel que la operación ya usa. |

### 45001 8.2 / 14001 8.2 — Respuesta ante emergencias

**Se exige:** procedimiento ante pérdida de control (*flyaway*), caída, incendio de
batería o pérdida de enlace; RTH configurado; extintor en terreno; **reporte de
incidentes a la DGAC**; registros de simulacros.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | LV-46: reportar accidente/daño desde la ficha de la aeronave crea una mantención de emergencia y cruza una alerta automáticamente. |
| Falta | El procedimiento en sí es un documento, y **ya tiene dónde vivir**: "Documentos de la empresa" es un repositorio real (`R4.6`) con el tipo `company-procedure` (`R4.8`) — falta subirlo. No hay registro de simulacros ni de **reporte a la DGAC como paso trazado**; ambos diseñados en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md) (`R7.6`): el reporte a la autoridad son dos campos, y los simulacros probablemente no necesitan modelo, solo un tipo de documento más. |

### 10.2 — No conformidades e incidentes

**Se exige:** registro y **análisis de causa raíz** de re-vuelos, levantamientos
rechazados e incidentes; acciones correctivas **con verificación de eficacia**; reporte a
la autoridad cuando corresponda.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | El tablero "Seguimiento de alertas" es el mecanismo de acción correctiva; las alertas generan tarjetas de seguimiento. Auditoría *append-only* de todos los cambios. |
| Falta | ~~Resolver una alerta no pide motivo ni causa raíz~~ **Resuelto** (`R6.2`, 2026-08-11): resolver a mano **exige** un motivo, guardado en `Alert.resolution_reason`; los llamadores automáticos siguen sin motivo a propósito (no hay humano a quien preguntar). Sigue faltando: **no hay verificación de eficacia**, y los re-vuelos y levantamientos rechazados no se modelan → `R7.6`. Diseño de ambos (reusando el patrón del recordatorio de `R6.5` para la eficacia) en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md). |
| ~~Brecha de evidencia~~ | ~~Completar la tarjeta en el tablero no resuelve la alerta~~ **Resuelto** (`R6.1`, 2026-08-10): el cierre es bidireccional. Detalle no obvio: tuvo que ser `post_save`, no `pre_save`, o la segunda escritura de `Alert.resolve()` se perdía. |

### 9.1.1 — Indicadores de desempeño

**Se exige:** KPI con meta, tendencia y acción cuando no se cumple. Sugeridos: precisión
lograda vs requerida, tasa de re-vuelos, horas de vuelo sin incidentes, disponibilidad de
equipos, cumplimiento de plazos.

| | |
|---|---|
| Estado | 🟡 |
| Hoy | El informe ejecutivo compara período contra período anterior con `valid_pct`, `expired` y `due_30`, etiquetando mejor/peor/igual. El reporte de estado documental agrega por centro de costo. |
| Falta | Los KPI actuales son **documentales**, no operacionales, y **su tendencia no puede moverse**: `valid_pct`/`expired`/`due_30` se evalúan siempre "a hoy" sin importar el período pedido, así que comparar período contra período da siempre "sin cambio" por construcción (hallazgo documentado en `R6.4`). Un KPI sin tendencia posible no es un KPI. **Diseño listo** (`R7.7`, 2026-08-11) en [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md): `ComplianceSnapshot` (un trabajo programado que guarda los totales del día) arregla la tendencia sin tocar nada existente y **no necesita ninguna decisión de negocio** — es por donde conviene seguir. Falta además la **meta** (`KpiTarget`) y la acción ante incumplimiento, que debe reusar el tablero o las no conformidades de `R7.6`, no ser un tercer mecanismo. **Dos KPI operacionales ya son calculables hoy**: disponibilidad de equipos (`Aircraft.status` + estados de taller de `R5.1`) y cumplimiento de plazos (fechas del permiso vs. del vuelo). |

---

## Resumen

| Estado | Cláusulas |
|---|---|
| ✅ Cubierto | 6.1.3/9.1.2 (cumplimiento legal DGAC) |
| 🟡 Parcial | 4.2, 6.1.3 (zonas/privacidad), **7.1.3**, **7.1.5**, 7.2, **8.1**, 45001 8.2, 10.2, 9.1.1 |
| ⬜ Brecha | 6.1 (riesgo por vuelo — la parte meteorológica sí cubierta), 8.4 (externos), 8.5.1/8.6 (calidad), 14001 6.1.2 (ambiental), 45001 6.1.2 (IPER) |

**Movimientos del 2026-08-11:** 7.1.5 pasó de ⬜ a 🟡 (`R7.3`); 7.1.3 y 8.1 ganaron
contenido real (`R7.1`/`R7.2`, `R8.1`); las 4 brechas restantes **tienen diseño
escrito** (`R7.4`–`R7.7`, ver [docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md))
aunque sigan sin implementar.

**Lectura:** AeroControl está fuerte donde la DGAC fiscaliza —vigencias, permisos,
documentación, trazabilidad de equipos— y débil en el resto del sistema de gestión:
riesgo operacional por vuelo, calidad del entregable y SST. Eso es coherente con cómo
nació el producto y no es un defecto de diseño; es el siguiente tramo.

**Distinción que conviene tener clara frente al auditor:** lo que falta ya **no** son
bugs ni evidencia que exista y no se vea — eso se cerró. Lo que falta son **dominios que
la app todavía no modela** (calidad del entregable, riesgo por vuelo, SST), y de tres de
ellos lo que bloquea no es código sino **decisiones de negocio**: los umbrales de RMSE y
GSD del contrato, el límite de jornada de vuelo, y las metas de los KPI.

### Lo que había que arreglar antes de que llegue el auditor — ✅ los 4, hechos

Eran cosas que ya funcionaban pero no se veían o no dejaban rastro. **Todas
cerradas entre el 2026-08-10 y el 2026-08-11:**

1. ~~`R1.1` — el calendario oculta las vigencias DGAC/JAC en su vista por defecto.~~
   **Hecho** (el servidor deriva los 9 tipos de evento; verificado en vivo que el
   feed trae el seguro JAC y las credenciales DGAC).
2. ~~`R5.2` — los movimientos de recursos no registran quién los hizo.~~ **Hecho**
   (las 3 vistas CRUD del padrón atribuyen autor, más un tercer caso que el plan
   no listaba: editar la ubicación de una aeronave).
3. ~~`R6.1` / `R6.2` — el cierre de acciones correctivas es inconsistente y sin
   causa raíz.~~ **Hecho** (cierre bidireccional alerta↔tarjeta, y resolver a mano
   ahora **exige** un motivo que queda en `Alert.resolution_reason`).
4. ~~`R4.1` / `R4.6` — el AOC y los procedimientos existen en `Z:` pero no en la
   app.~~ **Hecho del lado del código**: "Documentos de la empresa" es un
   repositorio real (búsqueda, categoría, CSV) y existen los tipos
   `aoc-certificate`, `company-procedure` y `monthly-non-operation-notice`
   (`R4.6`/`R4.8`). **Queda del lado del usuario subir el PDF del AOC** — no
   necesita despliegue, ver `HANDOFF.md`.

~~**Lo más barato con mayor efecto:** `R7.1` (horas de vuelo por aeronave).~~
**Hecho** (2026-08-10, mismo agregado que `R5.4`).

**Lo más barato con mayor efecto, ahora:** `ComplianceSnapshot` (parte de `R7.7`)
— sin historia guardada, la *tendencia* que exige 9.1.1 no se puede calcular, y
hoy los 3 KPI documentales siempre leen "sin cambio" por construcción. No
necesita ninguna decisión de negocio. Ver
[docs/dev/iso-r7-design-plan.md](dev/iso-r7-design-plan.md).

---

*Relacionado:* `MASTER_PLAN.md` → bloques `R1`–`R8`;
`docs/dev/adr-0002-coexistencia-aerolink.md` (cláusula 7.1.3 vía AeroLink);
`docs/compliance-setup.md` (activación del monitoreo).
