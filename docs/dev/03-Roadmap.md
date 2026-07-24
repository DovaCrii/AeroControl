---
tags: [aero-ops, roadmap]
---

# 🗺 Roadmap

> ⚠️ **Histórico.** Este documento no se había actualizado desde su redacción
> inicial y varias fases marcadas como pendientes ya estaban implementadas
> (ver AUDIT_CLAUDE.md F-12). Se corrigió el 2026-07-24 para reflejar el
> estado real del código. **Para el trabajo pendiente y su seguimiento vivo,
> la fuente de verdad es [MASTER_PLAN.md](../MASTER_PLAN.md).**

## Fase 0: Fundación ✅ (Completada)

- [x] Proyecto Django con 7 apps modulares
- [x] BaseModel con UUID, timestamps, archive pattern
- [x] Settings split (base/dev/prod)
- [x] Data directory isolation
- [x] Modelos, migraciones, admin
- [x] Templates Bootstrap 5 responsivos
- [x] Scripts PowerShell (setup, run, backup, verify)
- [x] Git + GitHub configurado

## Fase 1: Core CRUD + Compliance ✅ (Completada)

- [x] CRUD completo de documentos con upload
- [x] Version replacement workflow
- [x] Asociación documentos-entidades (ContentType)
- [x] Descarga de archivos (autenticada)
- [x] Generación de alertas programada
- [x] Lista de alertas con filtros y resolución
- [x] Badge de alertas no resueltas en sidebar
- [x] Búsqueda y filtro en todas las listas
- [x] Paginación en todas las listas
- [x] Búsqueda por texto en listas (SearchMixin)

## Fase 2: Operations & Maintenance ✅ (Completada)

- [x] Workflow permisos de vuelo (request → approve/deny → complete) con
  transiciones guardadas y permisos por acción
- [x] Bitácora de vuelos con operador/aeronave y validación cruzada contra
  el permiso
- [x] Calendario unificado de permisos, mantenciones, tareas y vencimientos
- [x] Historial automático de cambios de estado (`PermissionHistory`,
  `MaintenanceHistory`) con actor, estado previo/nuevo y notas

## Fase 3: Workboard & UX ✅ (Completada)

- [x] Kanban drag-and-drop (SortableJS) con reordenamiento persistido
- [x] Asignación de tareas a operadores
- [x] Etiquetas de prioridad y filtros (estado/etiqueta/prioridad/responsable)
- [x] Dashboard con gráficos (Chart.js: aeronaves, permisos, mantenimiento,
  tareas, vuelos mensuales)

## Fase 4: Importación & Reportes ✅ (mayormente completada)

- [x] Importación desde Excel (adaptador Capítulo 1 con hojas canónicas)
- [x] Carga normalizada Capítulo 1 (11 CC, 14 aeronaves, 41 operadores)
- [x] Buscador global (permisos de lectura por dominio; **ver AUDIT_CLAUDE.md
  F-14 — implementado pero sin enlace en la UI aún, MASTER_PLAN.md T5.3**)
- [x] Reportes Word/Excel (CSV, XLSX, DOCX del Workboard)
- [ ] Validaciones cruzadas de seguro, permiso y habilitación (pendiente:
  esos dominios aún no tienen fuente normalizada — ver BACKLOG.md)

## Fase 5: Evolución Arquitectura

- [x] Django REST Framework API layer (`/api/v1/workboard/tasks/`, token +
  sesión, permisos por objeto y tablero)
- [x] Roles y permisos multi-usuario (`bootstrap_roles`, grupos estándar,
  `KanbanBoardAccess` por tablero)
- [ ] Migración PostgreSQL en producción (parametrizado y documentado; falta
  el ensayo real con respaldo/rollback — ver MASTER_PLAN.md, diferido)
- [⏸] Separación frontend/backend (Vue.js/React SPA) — **diferida por
  decisión de arquitectura** (`docs/frontend-boundary.md`); no reconsiderar
  sin un requisito real de API independiente, offline o cliente móvil
