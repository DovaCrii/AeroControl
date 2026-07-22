# Backlog — AeroControl

## Fase 2: Operations & Maintenance
- [ ] Workflow permisos de vuelo (request → approve → complete) con transiciones de estado
- [ ] Bitácora de vuelos con operador/aeronave asociada
- [ ] Calendario de vencimientos y mantenciones
- [ ] Historial automático de cambios de estado en mantenimientos

## Fase 3: Workboard & UX
- [ ] Kanban drag-and-drop con SortableJS
- [ ] Asignación de tareas a operadores
- [ ] Etiquetas de prioridad y filtros por operador
- [ ] Dashboard con gráficos (Chart.js)

## Fase 4: Importación & Reportes
- [ ] Importación desde Excel (pandas + openpyxl)
- [ ] Carga normalizada del Capítulo 1
- [ ] Buscador global (Haystack o similar)
- [ ] Reportes Word y Excel exportables
- [ ] Validaciones cruzadas (seguro ↔ aeronave ↔ operador ↔ permiso ↔ habilitación)

## Fase 5: Evolución Arquitectura
- [ ] Django REST Framework — serializers, viewsets, API v1
- [ ] Separación frontend (Vue.js o React SPA)
- [ ] Migración a PostgreSQL
- [ ] Roles y permisos multi-usuario
- [ ] CI/CD con GitHub Actions

## Mejoras continuas
- [ ] Tests automatizados para modelos, views y commands
- [ ] Object-level permissions
- [ ] Audit logging de acciones administrativas
- [ ] Modo oscuro
- [ ] i18n para español
