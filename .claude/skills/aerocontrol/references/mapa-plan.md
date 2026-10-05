# Mapa de MASTER_PLAN.md

Índice de secciones con su rango de líneas, para leer **solo** lo necesario (`sed -n 'A,Bp' MASTER_PLAN.md`).
Generado el 2026-10-05 sobre `6fba910`; los rangos se desplazan al editar el plan: si no cuadran, regenerar con `grep -nE '^#{2,3} ' MASTER_PLAN.md`.

Casi todo el archivo es **historia ya resuelta** (la mayoría de las ~500 filas con estado están `✅`). Para lo abierto usar `scripts/plan_query.py --pending`, no leer secciones.

| Líneas | Sección |
|---|---|
| 9–30 | Rumbo a 1.0 (actualizado 2026-08-12 — leer esto primero) |
| 31–48 |   Lo que separa a esta app de una 1.0 ya no es código, es operación |
| 49–84 |   Qué queda, al 2026-08-12 |
| 85–92 |   Deuda técnica: política incremental (sin cambios) |
| 93–176 |   Retiros a medias: condiciones de cierre (medido el 2026-09-02) |
| 177–232 | Antecedentes: prioridades post-auditoría (2026-08-07) |
| 233–254 | Cómo usar este documento |
| 255–260 | Rama de trabajo |
| 261–328 |   Dónde retomar |
| 329–354 |   Estado de la base de datos real (2026-07-24) |
| 355–381 |   Puesta en producción real: VM `p340` (2026-07-29/30) |
| 382–393 |   Revisión en vivo del usuario sobre la app desplegada (2026-07-30) |
| 394–428 |   Inventario de ramas (TL.6, cruzado el 2026-07-24) |
| 429–463 |   Anatomía de R.10 / T5.1 (medido el 2026-07-25) |
| 464–529 |   Revisión 2026-07-25 (V.*) — seguridad, estabilidad, desempeño y UX |
| 530–545 |   Áreas de vuelo en KMZ — decidido el 2026-07-25, **SUPERADO el 2026-07-27** |
| 546–569 |   Deuda de `openspec/specs/` (TL.8, pendiente) |
| 570–583 | Estado actual (actualizado 2026-07-24 — FASE 0 + higiene de Bloque 0 cerradas) |
| 584–585 | Tablero de bloques |
| 586–597 |   FASE 0 — Estabilización inmediata `⛔ desbloquea todo` |
| 598–607 |   FASE 1 — Arquitectura y deuda crítica `⛔ requiere FASE 0` |
| 608–618 |   FASE 2 — Seguridad y permisos `⛔ requiere FASE 1` |
| 619–628 |   FASE 3 — Integridad de datos `⛔ requiere FASE 1 · CAMBIAR AHORA` |
| 629–638 |   FASE 4 — Testing `⛔ requiere FASE 0; parcial tras FASE 3` |
| 639–652 |   FASE 5 — UX y flujos operacionales `requiere FASE 0` |
| 653–676 |   FASE 5R — Legibilidad y consistencia visual (feedback de revisión en vivo 2026-07-24) |
| 677–846 |   Revisión en vivo 2026-07-30 — issues de formularios/UX `🔄 EN CAPTURA` |
| 847–860 |   FASE 6 — Nuevas funcionalidades `⏸ requiere FASE 0-3 cerradas` |
| 861–868 | Bloques de producto (plan externo integrado 2026-07-24) |
| 869–882 |   Ruta de ejecución (ORDEN OBLIGATORIO — no seguir el orden numérico) |
| 883–900 |   BLOQUE 1 — Integración Alertas ⇄ Kanban `rama codex/alertas-kanban` |
| 901–915 |   BLOQUE 2 — Notificaciones y programación `rama codex/notificaciones` `✅ COMPLETO` |
| 916–927 |   BLOQUE 3 — Mejoras UX del Kanban `rama codex/kanban-ux` `⏸ DIFERIDO (no ejecutar sin instrucción)` |
| 928–940 |   BLOQUE 4 — Robustez de reglas y deuda de datos `rama codex/reglas-datos` `✅ COMPLETO (parte en alcance)` |
| 941–952 |   BLOQUE 5 — Centro de administración operativo `rama codex/admin-center` `🔄 PARCIAL — panel de situación (B5.1/ |
| 953–966 |   BLOQUE 6 — Reportes ejecutivos y asistente `rama codex/reportes-ejecutivos` (6.1/6.2 en la ruta; 6.3 diferido) |
| 967–970 |   BLOQUE 6.3 — Asistente IA `⏸ DIFERIDO (requiere aprobación de diseño)` |
| 971–1006 |   BLOQUE GEO (7) — Editor geoespacial KMZ/KML `rama codex/geo-*` `⬜ PROPUESTA APROBADA — espera "go" de GEO-0` |
| 1007–1036 |   BLOQUE OPS (8) — Seguimiento de contratos, recursos y permisos `rama codex/ops-*` `✅ CERRADO 2026-07-27 — OPS- |
| 1037–1058 |   FASE L — Limpieza y orden del repositorio `puede correr en paralelo a FASE 0` |
| 1059–1064 | Detalle de las tareas de FASE 0 — ✅ completada 2026-07-24 |
| 1065–1070 |   T0.1 — Bloque `extrahead` duplicado *(PRIMERA TAREA)* |
| 1071–1075 |   T0.2 — Cierre de mantenimiento |
| 1076–1080 |   T0.3 — Gate que realmente falla |
| 1081–1085 |   T0.4 — Umbral de cobertura |
| 1086–1090 |   T0.5 — Compilación de plantillas en CI |
| 1091–1095 |   T0.6 — Sincronizar metadatos |
| 1096–1102 |   T0.7 — Formato |
| 1103–1109 | REVISIÓN POST-AUDITORÍA (2026-08-07) — bloques R1-R8 y X |
| 1110–1122 |   BLOQUE R1 — Bugs que ocultan información de cumplimiento `P0` |
| 1123–1139 |   BLOQUE R2 — Permiso de vuelo: numeración, edición y flujo `P0` |
| 1140–1155 |   BLOQUE R3 — Estandarización transversal `P1` — antes de importar |
| 1156–1190 |   BLOQUE R4 — Repositorio documental `P1` |
| 1191–1204 |   BLOQUE R5 — Trazabilidad y ciclo de vida `P1-P2` |
| 1205–1214 |   BLOQUE R6 — Alertas y reportes `P2` |
| 1215–1229 |   BLOQUE R7 — Base para la auditoría ISO `P2` |
| 1230–1486 |   BLOQUE LV-D — Revisión en vivo sobre producción, 2026-08-11 (post-despliegue) `P1` |
| 1487–1492 |   BLOQUE R8 — Clima y contexto operacional `P3` |
| 1493–1512 |   BLOQUE X — Contrato de coexistencia con AeroLink `P1` |
| 1513–1526 | Reglas de trabajo con agentes |
