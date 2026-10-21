# Espacio aéreo: AIP-Chile (ENR 5.1) como fuente primaria (LV-361)

> Estado: diseño (2026-10-21), nota interna no autoritativa. Decisión de la persona: la base a mejorar es el **AIP-Chile**; el mapa de Google «ZONAS SENSIBLES» es la versión cruda y queda como referencia. Complementa `docs/dev/espacio-aereo.md` (LV-357). Investigación del 2026-10-21; **no es dictamen legal**.

## 1. Dónde están los datos y de cuándo son

Todo cuelga de `https://aipchile.dgac.gob.cl/dasa/aip_chile_con_contenido/ais/2%20ENR%20Parte%202/`:

| Sección | Ruta bajo la base | Contenido |
|---|---|---|
| ENR 5.1 | `ENR 5 Zonas Prohibidas, Restringidas y Peligrosas/ENR 5.1-1 Zonas P, R, D.pdf` | 24 págs., PDF de texto (desde Word), sin escanear |
| ENR 5.2, 5.4, 5.6 | idem | «NO APLICABLE» |
| ENR 5.3 | idem | globos sonda (puntos) y tabla de volcanes (coordenadas **ambiguas**, ej. «17 72 S»; no resolver por cuenta propia) |
| ENR 5.5 | idem | parapente, alas delta, láser y RPAS en Iquique, **sin código SC** |
| ENR 2.1 FIR/UIR | `ENR 2 Espacio Aereo ATS/aENR 2.1-1 al ENR 2.1-8 …pdf` | texto |

- **Enmienda vigente: AMDT NR 67 del 06-AGO-2026** (AIRAC 8). La próxima, AMDT 68 el 26-NOV-2026. El volumen I no se enmienda cada 28 días (en 2026: ciclos 5, 8 y 12); entre medio cambian NOTAM y SUP.
- **No hay API de zonas** (probadas `/api/zones|zone|areas|enr|airspace|fir|…` → 404). El «Mapa Interactivo» (`/symfony/map`, OpenLayers) **no muestra zonas P/R/D**; solo sirve GeoJSON estático de las FIR (`/json/SC?Z.json`, modificados en 2018, sin propiedades) y usa endpoints POST de aeródromos, rutas, METAR, SIGMET, NOTAM por geometría.

## 2. Qué trae ENR 5.1 y qué tan parseable es

**80 zonas** (AMDT 67): 32 P, 37 R, 11 D (dos «zona peligrosa» sin código). Tres columnas ES/EN: (1) identificación, nombre/FIR y límites laterales; (2) límite superior sobre inferior («UNL/GND», «FL 450/MSL», «1000 FT AGL», «FL 195 VFR / 3000 FT IFR»); (3) observaciones y horario (H24, HJ, IVNO/VRNO, «activada por NOTAM», coordinación, frecuencias). **La columna 3 trae teléfonos y correos de funcionarios: datos personales, jamás a git ni a pantalla.**

Seis formatos de coordenada (`53 46 00 S 70 31 00 W`, `334403.74S/0704141.16W`, coma decimal, `201125S/0700815W`, segundos pegados, etc.).

| Tipo | Zonas | Confiabilidad del auto-parseo |
|---|---|---|
| Polígono por vértices | 54 | Alta (~95 % de vértices) **si** la extracción separa las columnas por posición (bbox), no por línea |
| Círculo (centro y radio) | 18 | Alta (~90 %); mezcla NM, «m» y «M»; ojo R74 «500m (0.3 NM)» |
| Arco con centro en VOR/DME | 4 (P10, R22, R25, R32) | Baja: los centros están en GEN 2.5/ENR 4.1, no en el texto |
| Sector radial desde VOR | 4 (R45–R48) | No automatizable (radiales magnéticos; R47 por tramos; R48 «exceptúa SC-P3») |

Casos difíciles reales: **orden de vértices que cruza el polígono** en SC-P84, P85, R52, R61, R62, R68, R72 y la D sin código de Iquique (así viene en el PDF; el KML los reordenó; el parser **no corrige solo**, marca para revisión); erratas (P51 `07 031 15 W`, P99 `48 .74W`, P15 `725149.95 W`, D13 `710636W`, P9 `33,31`); P14 repite el primer vértice; P23 tiene límite distinto para VFR e IFR.

## 3. Comparación con el KML

- **Del AIP que falta en el mapa de Google (30):** P9, P14, P15, P26, P59, P84–P87, P90–P100 (las 11 de la V División son de la AMDT 67), R32, R35–R38, R45–R48, R72. SC-R73 está sin código («PALACIO PEREIRA»).
- **Del mapa que no está en el AIP vigente:** SC-D12 (Paranal), SC-P77 (San Damián) y las 15 zonas navales de la Armada (ENR 5.1 no las trae).
- **Corrección a `espacio-aereo.md` §1:** SC-P51 **sigue vigente** (AMDT 67); no estaba vencida.
- **Diferencias de límites** (mayoría 0–100 m, digitalizado a mano): revisar R53 (1,16 km en un vértice), R69 (~670 m), R16 (~450 m sistemático), D33 (460 m), R67 (224 m) y el centro del círculo D5 (823 m corrido).

## 4. Licencia y condiciones de uso

GEN 0.0-1: «Copyright © Nº 126.475 DGAC - CHILE» y aviso «Consulte los NOTAM/SUP AIP/AIC». El pie del sitio (VIA56 S.A.) es del desarrollador web. **No hay términos de uso ni licencia que permita o prohíba expresamente reproducir o derivar; no se leyó GEN 1.1 completa.** Decisión de la persona: uso **interno**. Se aplica: atribución textual «Fuente: AIP-Chile, DGAC, AMDT NR 67 (06 AUG 2026), ENR 5.1. Referencial; consulte NOTAM/SUP vigentes», datos en la base y **fuera de git**, y una consulta opcional al Depto. AIS de la DGAC si algún día se quiere redistribuir. Precedente a sopesar: `apps/registry/data/aip_aerodromes.csv` ya versiona en el repo público datos derivados de `/api/aerodrome`.

## 5. Diseño

**Modelo** (sobre `AirspaceSnapshot`/`AirspaceFeature`): `source_kind` (`aip_enr51`, `aip_enr55`, `aip_fir_json`, `google_mymaps`), en snapshot `amdt_number`, `effective_date`, `pdf_sha256`, `status` (draft, in_review, published, rejected); **un snapshot vigente por fuente** (la restricción `airspace_one_current_snapshot` pasa de global a por `source_kind`); en feature `source_kind`, `lateral_text` (texto de la fuente tal cual, **sin datos personales**), `geometry_method` (polygon, circle, arc, sector), `parse_warnings`, `review_status`, `reviewed_by`, `reviewed_at`. La pantalla **solo dibuja** geometría AIP con `review_status=approved`; el resto muestra la ficha textual. `AirspaceCrossCheck` (código, feature AIP, feature Google, `max_vertex_m`, `median_m`, resultado: match, discrepancy, missing_in_google, missing_in_aip, google_only): se calcula, no se edita.

**Importador `import_aip_enr5`** (`--file`/`--url`, `--dry-run`): pdfplumber con palabras y bbox, tres columnas por la x de los encabezados «1 2 3»; bloques por código SC; valida rangos (lat −17 a −57, lon −66 a −110), min/seg < 60, polígono simple sin autointersección, radio con unidad reconocida; arcos y sectores con centro externo quedan «sin geometría» con aviso (el centro del VOR lo carga una persona desde GEN 2.5/ENR 4.1, nunca el parser); **descarta teléfonos y correos**; idempotente por `pdf_sha256`; lo cambiado se archiva.

**Revisión humana obligatoria:** pantalla de admin con permiso específico; por zona, lado a lado: recorte del PDF, texto extraído, geometría propuesta sobre el mapa y su forma en el KML con la distancia; aprobar, corregir o rechazar con `AuditEvent`; zonas con aviso (bowtie, errata, arco, sector) no se aprueban en lote; un snapshot se publica solo con todas sus zonas resueltas.

**Qué ve el usuario:** insignia «AIP AMDT 67» o «Solo mapa Google (no está en el AIP vigente)»; «Diferencia con Google: X m» sobre un umbral que fija la persona; capa «referencia Google» apagada por omisión (D12, P77, navales); el aviso fijo «Referencial».

**Actualización:** un comando/timer revisa cada 28 días la fecha del PDF y su sha y avisa si hay enmienda; nunca publica solo; la foto pasa a ámbar cuando `effective_date` es anterior a la última AMDT conocida.

## 6. Decisiones (tomadas según lo recomendado; la persona puede revertirlas)

1. Datos fuera de git; atribución textual; consulta a la DGAC solo si se quiere redistribuir.
2. **El umbral de discrepancia en metros lo fija la persona** (hasta entonces el cruce muestra la distancia sin juicio de color).
3. R45–R48 (sectores con radiales magnéticos): solo como texto hasta que la persona entregue la regla.
4. D12, P77 y las navales se conservan como capa «referencia Google».
5. Quien revisa y aprueba cada enmienda: la persona (o a quien designe).
6. Los volcanes de ENR 5.3 quedan fuera hasta aclarar el formato de coordenadas.

## 7. Fases (un PR por fase)

1. Campos de fuente y revisión, restricción por fuente (**migración**); arreglo menor: `KINDS` duplicado en `apps/airspace/models.py`.
2. Parser de ENR 5.1 como funciones puras, con pruebas sobre **texto sintético** (seis formatos, erratas, bowtie; sin PDF real en git).
3. Comando, snapshot en borrador y tabla de cruce.
4. Pantalla de revisión en admin (403 sin permiso).
5. Capa AIP en `/environment/airspace/`, insignias y FIR desde `/json/*.json` (estáticos y `.mo`).
6. Opcional: ENR 5.5, globos sonda, arcos y sectores con el centro VOR cargado a mano.

Riesgos: una coordenada mal leída se ve tan creíble como una buena (revisión y cruce); la maquetación del PDF puede cambiar sin aviso; entre enmiendas mandan NOTAM y SUP, que la app no incorpora; datos personales en observaciones; licencia sin texto expreso.
