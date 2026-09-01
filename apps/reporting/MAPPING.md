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

## Notas de arquitectura que ya están decididas

1. **`ComplianceSnapshot` existe y hace lo que `ReportRun.payload` quiere**: es
   append-only, una fila por (fecha, centro de costo) más la consolidada, y su
   docstring dice que existe "to make trend possible". Antes de crear
   `ReportRun`, ver si el snapshot cubre el congelado y `ReportRun` sólo necesita
   referenciarlo.
2. **El PDF no usa WeasyPrint.** El repo eligió `reportlab` a propósito: "pure
   Python, no system package (Cairo/Pango, wkhtmltopdf) required on the Ubuntu VM
   deploy". `apps/core/pdf.py` ya genera PDF con el membrete JEJ (`LV-144`).
   Decidido con el usuario: HTML en la app primero, PDF automático después.
3. **`openpyxl` ya es dependencia** — el anexo XLSX no necesita nada nuevo.
4. **El envío por correo está bloqueado**: SMTP es el único criterio en rojo del
   proyecto. Generar, ver y aprobar el informe **no** depende de él; enviarlo sí.
5. **Semáforo del CC = el peor de sus habilitantes**, no el promedio (§4.2). Un CC
   con cuatro verdes y un rojo es rojo.
