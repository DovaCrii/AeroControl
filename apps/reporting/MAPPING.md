# Informe Mensual RPA — mapeo campo → modelo real

Cada hoja del payload de `SPEC_REPORTE_MENSUAL_RPA.md` §3, contra lo que existe
hoy en el repo. **La especificación no asume nombres de modelos a propósito**, y
este archivo es la contraparte: dice de dónde sale cada dato.

Se escribe antes del código de render porque la §6 del SPEC ("datos que
probablemente falten") **acertó en dos de siete y erró en el que marcaba como
bloqueante**. Sin este mapeo, R2–R4 vuelven a construir lo que ya está.

> **Regla que manda sobre todo lo demás**: el informe nunca inventa un dato.
> Sin valor en la base, el campo se renderiza como pendiente (ámbar punteado), no
> como cero. `valor: null` es un resultado válido y esperado.

---

## ⚠️ La estructura real del informe emitido, que difiere del SPEC

El informe de agosto **ya se emitió** a la DGAC:
`OneDrive/DGAC/INFORMES/Agosto2026/JEJ-GTE-CT-INF-RPA-2026-08_Agosto2026.pdf`.
**Ese PDF, y no la especificación, es la referencia de qué hay que producir** — el
SPEC describe 6 artboards y el informe emitido tiene **5 páginas** con otra
división:

| Página | Contenido | De dónde sale |
|---|---|---|
| 1 | Portada: código, período, elaborado por / dirigido a, alcance del ciclo, fecha de corte, estándar `JEJ-GRI-SS-INS-096 Rev. 0` | Constantes + período |
| 2 | **1 Resumen ejecutivo**: 6 indicadores en tarjetas + 4 hallazgos redactados | Cifras de la base; **hallazgos escritos a mano** |
| 3 | **2 Permisos vigentes**: el ciclo de 4 pasos, una observación del período, y la tabla de 11 permisos (N° JEJ, N° DGAC, CC, operadores, aeronaves, vigencia, días) + las solicitudes en trámite | Tabla de la base; **observación escrita a mano** |
| 4 | **3 Cobertura por Centro de Costo**: tabla de 12 faenas con permisos vigentes, próximo vencimiento, días y estado; más cobertura del padrón y concentración operacional | Todo de la base |
| 5 | **4 Plan de normalización**: 4 fases con criterio de cierre + tabla de exigibilidad progresiva | **Todo escrito a mano** (ver `LV-227`) |

**Los indicadores reales del cierre de agosto**, útiles como caso de prueba de los
colectores: 12 faenas registradas con operación RPA, 11 permisos vigentes, 7 de 12
faenas **sin** permiso vigente, 4 permisos por vencer en 60 días (uno en 17), 3
solicitudes en trámite, 0 incidentes. Del padrón de 41 operadores y 14 aeronaves,
sólo 10 y 6 están designados en permisos vigentes.

⚠️ **El dato que evita corromper datos reales**: *"la vigencia otorgada no es
uniforme. De los 11 permisos vigentes, 7 fueron autorizados por 3 meses y 4 por 2
meses. El calendario de renovación debe construirse sobre la fecha real de cada
resolución, nunca sobre un plazo supuesto."* Por eso `LV-224` **valida** el techo
de 3 meses y no calcula el vencimiento: calcularlo habría falseado 4 de 11.

✅ **La Fase 1 del plan (comprometida para octubre) ya está implementada**:
`LV-224` (vencimiento sobre la fecha real de cada resolución), `LV-225` (carta del
mandante) y `LV-226` (alertas 45/30/15 con el escalamiento del reparto de roles que
el informe describe). Desplegado el 2026-09-01.

Y la Fase 2 (noviembre) pide que *"el sistema no admita registrar un vuelo sin
permiso vigente en esa fecha"* — la mitad de eso la dejó puesta `LV-219`, que
rechaza un vuelo contra un permiso sin vigencia; la validación del rango de fechas
ya existía.

## Estado de la §6 del SPEC

| § | Dato | Estado | Dónde |
|---|---|---|---|
| 6.1 | Permiso con emisión, vencimiento y carta | **Existe** | `FlightPermission`. La carta del mandante se sumó en `LV-225`; el techo de 3 meses en `LV-224` |
| 6.2 | `especialista_documental` en Centro de Costo | **Falta** | — |
| 6.3 | Vencimiento de licencia y seguro JAC | **Existe** | `Qualification.expiry_date`, `Aircraft.insurance_expiry` (`LV-29`) |
| 6.4 | Registro DGAC de la aeronave con vigencia | **Falta** | Hay `Aircraft.registration` (matrícula), sin vigencia asociada |
| 6.5 | Capacitación operador ↔ modelo | **Por confirmar** | `QualificationType` es "DGAC rating per aircraft family": falta saber si la familia basta |
| 6.6 | Vuelo ↔ bitácora / checklist / inspección | **Por confirmar** | `FlightRecord` y `DocumentType.is_operational_record`; los tres códigos existen (`flight-log`, `rpa-checklist`, `drone-inspection`) |
| 6.7 | Incidentes según Anexo H | **Por confirmar** | `NonConformity` (R7.6), sin comparar contra el Anexo |

---

## `meta`

| Campo | Origen |
|---|---|
| `periodo`, `corte` | Argumento del command |
| `codigo` | Se compone: `JEJ-GTE-CT-INF-RPA-<periodo>` |
| `emite`, `en_conjunto_con` | Constantes del estándar `JEJ-GRI-SS-INS-096` |

## `kpis`

**Casi todos ya calculados.** No reimplementar: llamar.

| Campo | Función que ya lo da |
|---|---|
| `cc_con_operacion` | `CostCenter.objects.filter(is_active=True, operates_flights=True)` — `operates_flights` es de `LV-205`: `CC110`/`CC410` administran equipos y no vuelan |
| `permisos_operacion_vigentes` | `apps.compliance.kpis.permit_counts(today)["in_force"]` |
| `aeronaves_flota`, `operadores_registrados` | `Aircraft` / `Operator` activos |
| `operadores_licencia_vigente` | `Qualification.expiry_date` — ver `upcoming_expirations` para el patrón |
| `rpa_seguro_y_registro` | `Aircraft.insurance_expiry` **más el registro DGAC, que falta** (§6.4) → parcial |
| `vuelos_del_mes` | `FlightRecord` por `actual_date` en el período |
| `pct_habilitantes_vigentes` | Derivado del semáforo por CC (§4.2) |
| `pct_bitacoras_cargadas` | Depende de §6.6 → **pendiente** |
| `incidentes` | `NonConformity` en el período |

`operational_kpis()` agrupa varios de estos y trae además `on_time_execution` y
`survey_accuracy`, que el informe no pide pero existen.

## `centros_costo[]`

Punto de partida: **`permit_status_by_cost_center(today)`** (`LV-206`), que ya
parte de las faenas y no de los permisos — precisamente para que las que **no
tienen** ninguno aparezcan, que es lo que el informe quiere mostrar.

| Campo | Origen |
|---|---|
| `codigo`, `nombre` | `CostCenter` |
| `rpa`, `operadores` | Conteos por `cost_center` |
| `seguro_jac` | `Aircraft.insurance_expiry` → semáforo |
| `licencias` | `Qualification.expiry_date` → semáforo |
| `registro_dgac` | **Falta el dato** (§6.4) → `null` |
| `permiso_operacion.emitido` / `.vence` | `FlightPermission.valid_from` / `.valid_until`. ⚠️ **Pueden ser nulos** desde `LV-219`: un permiso solicitado no tiene vigencia, y eso no es "vencido" ni "vigente" |
| `permiso_operacion.dias_restantes` | `valid_until - corte`; `null` si no hay vigencia |
| `permiso_operacion.carta_mandante_solicitada` | Documento `client-authorization-letter` en el expediente (`LV-225`). `check_client_letters` ya hace esta consulta |
| `docs_nextcloud` | Sin equivalente; el repositorio documental es `Z:` (`import_document_repository`) |
| `especialista_documental` | **Falta el campo** (§6.2) → `null` |

## `dotacion`

`flota.por_modelo` sale de `Aircraft.model`, que es texto libre — así que los
cuatro modelos que el SPEC enumera hay que agruparlos contra los valores reales,
no asumirlos.

## `vencimientos_60d`

Todo esto lo responde ya **`upcoming_expirations(today, cutoff)`**
(`apps/dashboard/views.py`), que cubre habilitaciones, credenciales DGAC, seguros
JAC, documentos y permisos, cada uno con su enlace. `cartas_mandante` se suma
ahora que la carta es un tipo de documento con fecha opcional (`LV-225`).

## `brechas[]` y `compromisos_mes_anterior`

`NonConformity` tiene el flujo de hallazgo con responsable y plazo. Los
compromisos del mes anterior se leen del `ReportRun` previo, no se recalculan.

---

## Estado de la implementación

**R0/R2 hechos** (2026-09-01): `apps/reporting/` con `ReportRun` (migración
`reporting.0001`) y `builder.py`, que arma `meta`, `kpis` y `cost_centres`
llamando a las funciones que ya existían. 20 tests.

**R3 hecho** (2026-09-02), junto con `UX-06`: las cinco páginas en
`templates/reporting/`, la hoja A4 en `static/css/report-a4.css` y la vista
`/reporting/monthly/` (`reporting.view_reportrun`). Dibuja el `payload`
congelado si hay `ReportRun` del período y una vista previa en vivo si no, y lo
**declara en pantalla**: en el papel los dos son idénticos. 20 tests más.

⚠️ **Tres cosas del ZIP que conviene no volver a averiguar:**

1. **Son ocho plantillas y cinco páginas.** `p3_habilitantes` y `p4_dotacion`
   son variantes que no llegaron al PDF emitido —el `build_pdf.py` del propio
   ZIP arma `Main · Resumen · Permisos · Cobertura · Plan`— y `dato_ejecutivo`
   es **otro documento**, una hoja mensual aparte con su propio PDF.
2. **Las plantillas ya venían con `{% load static %}`** y `{% static %}`, así
   que el ZIP se escribió pensando en Django.
3. **`build_pdf.py` usa WeasyPrint**, que este repo descartó a propósito. No es
   la ruta del PDF: sirve como referencia de en qué orden van las páginas.

Lo que **falta**: R4 (semáforos, la tabla permiso a permiso, el próximo
vencimiento por faena y la concentración operacional), R5 (command y vista de
aprobación), R6 (XLSX y envío, bloqueado por SMTP) y R7 (bitácoras, depende de
§6.6). La narrativa —hallazgos y observación del período— es `LV-227`, no un
bloque R.

⚠️ **Deuda declarada de R3 que R4 tiene que cerrar**: el informe emitido cuenta
los permisos por vencer en **60 días** y el payload sólo trae la ventana de
**30**, que es la que `permit_counts` calcula. La tarjeta se rotula por lo que
mide; sumar la ventana de 60 va con los semáforos.

## El corte temporal, y hasta dónde llega

**Hecho el 2026-09-02.** `panel_readiness` recibía la fecha de corte y la usaba
sólo para **comparar vencimientos**; la población salía de
`filter(is_active=True)`, o sea el padrón **actual**. Medido en producción: el
payload de agosto devolvía **42 operadores** y el informe emitido a la DGAC
decía **41**. Ahora la flota y el padrón se acotan además con
`created_at__date <= cutoff`.

**Va sin parámetro y siempre**, y eso es deliberado: con la fecha de hoy la
condición es verdadera para toda fila, así que **el panel no cambia** — y una
segunda función "igual pero con corte" es cómo el panel y el informe empiezan a
discrepar (`LV-188`, `LV-201`).

⚠️ **Lo que el corte NO hace, y hay que decirlo porque el informe va firmado:**

| Sí | No |
|---|---|
| Deja de contar lo que todavía no existía en la base | Reconstruir el padrón de esa fecha |
| Impide que un informe emitido engorde al cargarse fichas después | Saber quién estaba archivado entonces (no hay historial de `is_active`) |
| — | Distinguir la fecha del hecho de la fecha de carga: una ficha cargada a destiempo lleva su `created_at` de carga |

Es una **cota superior honesta, no una foto**. Archivar una ficha la saca
también de los informes anteriores, y hay un test que fija exactamente eso para
que nadie lea de más. **La cifra sólo queda estable cuando el informe se
congela** (`R5`): un `ReportRun` dibuja su payload guardado y ya no depende de
esta consulta.

**Cómo medirlo en la VM antes y después de desplegar** — el número tiene que
bajar de 42 a 41, y si no baja es que `created_at` refleja la fecha de carga
masiva y no la del hecho:

```
uv run python manage.py shell -c "from datetime import date; from apps.dashboard.views import panel_readiness; print({c['key']: (c['count'], c['total']) for c in panel_readiness(date(2026,8,31))['readiness']})"
```

## "Sin fecha" no es "vencida"

El informe emitido decía **8 sin credencial vigente**; eran **7 sin fecha más 1
vencida**, y se arreglan distinto — una es cargar un dato que nadie ingresó, la
otra es un trámite ante la DGAC. Sumadas, la cifra no dice a quién llamar, y
además no conversa con el resto del documento: una fecha ausente **no genera
alerta** (`LV-29`: un nulo es "nunca se ingresó") ni aparece en la lista de
vencimientos. El panel ya hacía la distinción desde `LV-129`; el payload la
heredaba sumada y ahora trae `insurance_missing`/`insurance_lapsed` y
`credentials_missing`/`credentials_lapsed`.

## Notas de arquitectura que ya están decididas

1. ~~**`ComplianceSnapshot` existe y hace lo que `ReportRun.payload` quiere**~~ —
   **verificado y descartado**: ese modelo guarda seis contadores documentales en
   **columnas fijas** (`total`, `valid`, `expired`, `due_7/15/30`) por (fecha,
   faena), y existe para dar tendencia **diaria**. El informe es un payload
   heterogéneo emitido una vez al mes y sujeto a aprobación; meterlo ahí obligaría
   a colgar un JSON de una tabla de contadores y a convertir un registro diario en
   mensual. `ReportRun` **lee** snapshots cuando necesite tendencia: son fuentes,
   no rivales.
1. ⚠️ **El SPEC se contradice sobre la unicidad del período**, y se resolvió: su
   §1.1 pide `unique_together = [("periodo",)]` y su §5.1 dice que `--force`
   *"crea una versión nueva, no sobrescribe"*. `ReportRun` usa `(period,
   revision)`: el informe es un documento controlado —la portada del de agosto
   dice "Revisión 0"—, así que la revisión es parte de su identidad.
1. **`missing_fields` se guarda, no se recalcula.** El informe tiene que seguir
   diciendo qué faltaba **cuando se emitió**: si se recalculara, el de agosto
   mejoraría solo al cargarse los datos en septiembre y desaparecería la evidencia
   de la brecha que reportó. Misma lección que `LV-118` dejó en las alertas.
1. **Cero no es ausente.** Un cero afirma ("hay cero"), `None` es la ausencia de
   afirmación ("no se sabe"). Un `if not value` en `find_missing` los mezcla, y
   con ellos el informe puede declarar cumplimiento sobre un hueco de carga — va
   firmado ante la DGAC. Hay un test que lo fija, verificado rompiéndolo.
2. **El PDF no usa WeasyPrint.** El repo eligió `reportlab` a propósito: "pure
   Python, no system package (Cairo/Pango, wkhtmltopdf) required on the Ubuntu VM
   deploy". `apps/core/pdf.py` ya genera PDF con el membrete JEJ (`LV-144`).
   Decidido con el usuario: HTML en la app primero, PDF automático después.
3. **`openpyxl` ya es dependencia** — el anexo XLSX no necesita nada nuevo.
4. **El envío por correo está bloqueado**: SMTP es el único criterio en rojo del
   proyecto. Generar, ver y aprobar el informe **no** depende de él; enviarlo sí.
5. **Semáforo del CC = el peor de sus habilitantes**, no el promedio (§4.2). Un CC
   con cuatro verdes y un rojo es rojo.
