# Análisis de competencia y ruta de escala — 2026-08-14

> Pedido del usuario: analizar las recomendaciones de Codex, ver cómo acercarse a
> DroneLogbook y AirData, evaluar si conviene usar herramientas existentes, y
> proponer mejoras de UX/UI y una ruta para "pasar a una etapa superior".
> Nota interna (`docs/dev/`), no autoritativa: las decisiones que salgan de acá
> se capturan como filas en `MASTER_PLAN.md`.

## 1 · Qué hacen los referentes, en concreto

**AirData UAV** (~260.000 usuarios, nube): su corazón es la **ingesta automática
de telemetría** — los vuelos se sincronizan solos desde DJI/Autel/Skydio/Parrot y
40+ apps, sin que el piloto haga nada. Sobre eso construye: análisis de baterías
**celda por celda** después de cada vuelo (alerta cuando una celda deriva, antes
de perder la aeronave), mantenimiento programado por horas de vuelo/ciclos/
calendario, reportes de cumplimiento exportables para la autoridad, alertas por
umbral, y como extras empresariales streaming en vivo y LAANC (autorización de
espacio aéreo — sólo EE.UU.).

**DroneLogbook**: importación de bitácoras desde **80+ formatos** con
reproducción 3D de la traza GPS, **checklists y evaluaciones de riesgo digitales
personalizables**, inspecciones programadas por vuelos/horas/días, vigencia de
pilotos, documentos con control de vencimiento, y reportes de cumplimiento por
agencia (FAA, CAA, CASA, EASA… incluye plantillas "DGAC" genéricas).

## 2 · El mapa honesto: qué de eso ya tiene AeroControl

Esta comparación sorprende para bien. Contra la lista de funciones de ambos:

| Capacidad del referente | AeroControl hoy |
|---|---|
| Registro de flota, pilotos, vigencias | ✅ Padrón completo + vigencias con alertas y digest diario |
| Documentos con vencimiento | ✅ Y con más profundidad: versiones, categorías (LV-95), antivirus, escalera del seguro JAC (LV-81) |
| Reportes para la autoridad | ✅ Reporte de cumplimiento CSV/XLSX/DOCX/PDF + cumplimiento mensual + espejo DGAC |
| Vigencia de pilotos | ✅ Credenciales + habilitaciones + compatibilidad operador-aeronave |
| Mantenimiento con inspecciones | ✅ Con trazabilidad del camino real (casa/taller, LV-82) |
| Evidencia meteorológica | ✅ `WeatherReview` (R8.2): queda registrada, con acción explícita — **la recomendación #5 de Codex está vencida en esta mitad** |
| Alertas por umbral | ✅ Motor de reglas + estados terminales declarados (LV-90) |
| Trazabilidad auditable | ✅ Estilo SIGO (LV-72) + `AuditEvent` append-only — **más fuerte que lo que muestran ambos referentes** |
| KPIs operacionales | ✅ Los 5 de la guía ISO (R7.7) + panel "¿puedo operar hoy?" (LV-89) |
| **Ingesta automática de vuelos** | ❌ `FlightRecord` es manual. **Esta es LA brecha** |
| Análisis de baterías por celda | ❌ Espejo de inventario (X.4b) sí; análisis necesita telemetría |
| Checklists/riesgo **digitales** | ❌ Existen como PDF escaneado (LVE-002/003); el IPER estructurado es `R7.5`, ya capturado |
| Mantenimiento por horas de vuelo | ❌ Programable por fecha; por horas necesita horas reales → misma brecha |
| Reproducción 3D de trazas | ❌ Los planes geo muestran el área, no el vuelo ejecutado |
| LAANC / streaming | — No aplican en Chile / descartados a propósito (correcto) |

**Lectura**: AeroControl ya es mejor que ambos referentes en el eje
**cumplimiento DGAC chileno** — que es el negocio. Lo que no tiene es el eje
**telemetría**: todo lo que falta (baterías por celda, mantenimiento por horas,
trazas ejecutadas, conciliación de bitácoras) cuelga de **una sola** capacidad
ausente: que los vuelos entren solos. Eso es exactamente `X.4`.

## 3 · Las 6 recomendaciones de Codex, evaluadas

1. **"Desplegar la tanda actual"** — ✅ **Hecho el 2026-08-14** (migración
   `compliance/0019` aplicada en `p340`, verificado). Superada.
2. **"Cerrar la brecha de datos, no de código"** — **De acuerdo, sin matices.**
   Es `LV-74` (8 vigencias nulas) + las 3 correcciones de fichas. Un nulo no
   genera alerta: es el único riesgo operativo *hoy*.
3. **"Prioridad de producto: sesiones de vuelo desde AeroLink (`X.4`)"** — **De
   acuerdo, y el mapa de arriba lo confirma**: es la única brecha real contra los
   referentes, y desbloquea cuatro funciones de una vez. Ver §5.
4. **"Expediente operativo del permiso"** — **De acuerdo; es la mejor idea UX de
   la lista.** Ver §6.1.
5. **"Persistir evidencia meteorológica y crear IPER"** — **Mitad vencida, mitad
   ya capturada**: `WeatherReview` existe desde R8.2 (queda como evidencia, con
   quién y cuándo); el IPER estructurado es `R7.5`, fila abierta.
6. **"Mantener foco local-first, no copiar LAANC/streaming"** — **De acuerdo.**
   La DGAC no publica API estable; un dato de espacio aéreo desactualizado es
   peor que ninguno.

## 4 · ¿Comprar una herramienta o seguir construyendo?

**Recomendación: no comprar, tomar prestados los patrones.** Razones:

- Lo que un SaaS haría bien (telemetría) **ya tiene un camino propio**: AeroLink
  es interno, habla con la flota real de JEJ, y `X.4b` (baterías) ya demostró el
  patrón espejo. Pagar AirData para eso duplicaría el camino con datos saliendo
  a una nube de terceros.
- Lo que AeroControl hace bien **ningún SaaS lo hace**: escalera del seguro JAC,
  espejo del formulario DGAC, folio SIGO, cumplimiento mensual chileno,
  repositorio `Z:`, español institucional. Las plantillas "DGAC" de DroneLogbook
  son genéricas, no el formulario que JEJ presenta.
- **Local-first es una decisión ya tomada** (AGENTS.md): datos operativos y de
  clientes dentro de la intranet.

Lo que sí vale **copiar como patrón** (no como dependencia): la ingesta sin
fricción (§5), el expediente por operación (§6.1), y — más adelante, con
telemetría real — las alertas de degradación de batería por tendencia.

## 5 · La brecha que importa: el contrato de sesiones con AeroLink (`X.4`)

El salto de etapa no es una pantalla: es que **las horas de vuelo y los ciclos
dejen de depender de lo que alguien escriba**. Propuesta de forma (para discutir
con el lado AeroLink):

- **Contrato JSON versionado** (`session.v1`): serial de aeronave, operador,
  inicio/fin, duración, baterías usadas con ciclos, home point, y opcionalmente
  la traza. AeroLink **empuja** al endpoint token-autenticado que ya existe
  (`apps.core.api`, movido justamente para esto en LV-78 paso 1).
- **Conciliación, no reemplazo**: cada sesión entrante busca su `FlightRecord`
  (mismo día + aeronave + permiso vigente); si existe, adjunta telemetría; si
  no, crea uno marcado `origen: aerolink` para que operaciones lo confirme. El
  patrón idéntico ya funciona en `sync_batteries` (X.4b) — reusar su forma.
- **Qué desbloquea, en orden**: horas reales por aeronave → mantenimiento por
  horas (como AirData) → ciclos reales de batería → `on_time_execution` y los
  KPI dejan de ser optimistas → traza ejecutada sobre el plan geo (comparación
  planificado-vs-volado, hoy diferida en GEO-14).

**Dependencia dura**: el PR de AeroLink (pendiente del usuario) y que AeroLink
llegue a emitir sesiones cerradas. Hasta entonces, del lado AeroControl se puede
dejar **el contrato escrito y el endpoint aceptándolo** — igual que X.4b esperó
su lado.

## 6 · Mejoras UX/UI propuestas (de mayor a menor valor/costo)

### 6.1 Expediente operativo del permiso *(la idea #4 de Codex, hecha propuesta)*

Una pestaña **de sólo lectura** en la ficha del permiso que responda *"¿esta
operación está completa?"* sin saltar entre módulos: permiso + estado con
trazabilidad · plan geo con su revisión meteorológica · aeronaves con seguro y
aeronavegabilidad vigentes (semáforo) · operadores con credencial vigente ·
documentos del permiso (carta + autorización firmada) · vuelos registrados ·
faltantes **nombrados** (“falta: bitácora del 08-12”). Cero datos nuevos — es la
misma composición que el panel LV-89 hace para la flota, aplicada a una
operación. Es también la respuesta estructural a `LV-104` (revisar una carpeta
antes de auditoría) y donde `LV-92` (visor PDF en modal) rinde más.

### 6.2 La bandeja de alertas como centro real

El usuario declaró que **vive en alertas, no en el calendario** (LV-103). Eso
sugiere: arreglar su N+1 (`LV-106`, medido: 62 consultas con 21 alertas),
y si el calendario se reduce, traer su única pregunta útil ("¿qué vence esta
semana?") al panel como **lista compacta**, no como grilla mensual — una grilla
de 35 celdas con 4 eventos es casi toda aire.

### 6.3 Documentos que aguanten volumen (`LV-104`)

Las categorías de LV-95 ya son facetas naturales: filtro por categoría en los
repositorios, agrupación visual en la ficha, orden por vencimiento. Con el
importador R4 (~cientos de archivos de `Z:`) esto pasa de estética a necesidad.

### 6.4 Identidad visual en lo que sale de la app

Los PDF del reporte con membrete JEJ (`reportlab` ya está instalado — criterio
"más empresarial" de 1.0). Es lo único de esta lista que un cliente o un
inspector DGAC **ve directamente**.

### 6.5 Micro-arreglos ya capturados

`LV-99` (Cancelar vuelve a la ficha), `LV-100` (campos ignorados en reemplazo),
`LV-105` (botón Filtrar deforme), `LV-65` (desplegable de aeronaves con más
contexto).

## 7 · La ruta de etapas

- **Etapa actual → 1.0 "operación confiable"** *(semanas, casi nada es código)*:
  datos completos (LV-74 + 3 fichas), monitoreo mínimo (uptime + errores — el
  único criterio de 1.0 que no existe en absoluto), correo corporativo
  verificado, restauración como rutina escrita, LV-101 (la puerta trasera de
  estados, P1), LV-97 (lote×antivirus, decidir `clamdscan`).
- **1.x "la app que se consulta sola"** *(el trabajo UX de §6)*: expediente del
  permiso, LV-92, documentos con facetas, membrete, decisión del calendario.
- **2.0 "los datos entran solos"** *(el salto estratégico)*: contrato `X.4` +
  conciliación; después mantenimiento por horas, ciclos reales, IPER (R7.5)
  sobre datos verdaderos. Recién aquí AeroControl compite con AirData **en el
  eje de AirData** — habiendo ganado ya en el eje DGAC.
- **PostgreSQL**: sigue donde estaba — cuando haya usuarios concurrentes reales
  (`docs/postgresql-readiness.md`), no antes.

## Fuentes

- [AirData UAV — features](https://airdata.com/features) · [sitio](https://airdata.com/)
- [DroneLogbook — features](https://www.dronelogbook.com/hp/1/features.html) · [sitio](https://www.dronelogbook.com/)
- [Aloft Air Control](https://www.aloft.ai/air-control/) (referente de flujo, descartado para Chile)
- [DGAC Chile — operación de drones](https://www.dgac.gob.cl/operacion-de-drones/)
