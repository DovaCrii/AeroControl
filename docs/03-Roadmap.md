---
tags: [aero-ops, roadmap]
---

# 🗺 Roadmap

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

## Fase 2: Operations & Maintenance

- [ ] Workflow permisos de vuelo (request → approve → complete)
- [ ] Bitácora de vuelos con operador/aeronave
- [ ] Calendario de vencimientos y mantenciones
- [ ] Historial automático de cambios de estado

## Fase 3: Workboard & UX

- [ ] Kanban drag-and-drop (SortableJS)
- [ ] Asignación de tareas a operadores
- [ ] Etiquetas de prioridad y filtros
- [ ] Dashboard con gráficos

## Fase 4: Importación & Reportes

- [ ] Importación desde Excel
- [ ] Carga normalizada Capítulo 1
- [ ] Buscador global
- [ ] Reportes Word/Excel
- [ ] Validaciones cruzadas (seguro ↔ aeronave ↔ operador ↔ permiso)

## Fase 5: Evolución Arquitectura

- [ ] Django REST Framework API layer
- [ ] Separación frontend/backend (Vue.js/React SPA)
- [ ] Migración PostgreSQL
- [ ] Roles y permisos multi-usuario
