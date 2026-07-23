---
tags: [aero-ops, seguimiento]
---

# 📝 Seguimiento

## Sesión 1 — 14 Julio 2026

### Qué se hizo
- Proyecto Django creado desde cero con 7 apps modulares
- Todos los modelos, migraciones, vistas, templates, URLs
- Tema visual navy/turquoise con Bootstrap 5
- Separación code/data (AeroOpsDesk_Data fuera del repo)
- README.md profesional con diagrama de arquitectura
- ARCHITECTURE.md con plan de evolución back/front
- LICENSE MIT
- Repositorio GitHub creado y push inicial
- SDD Init + openspec bootstrap
- Document Management UI completo (upload, replace, download, soft delete)
- Alert generation command + list/resolve UI
- SearchMixin + búsqueda/filtro en todas las listas
- Paginación y templates formateados
- Documentación Obsidian-friendly en docs/

### Decisiones
- **Nombre**: AeroControl (repo: aero-ops-desk)
- **Stack**: Django 6.0 + Bootstrap 5 (monolito inicial)
- **Licencia**: MIT
- **SDD**: OpenSpec, modo automático

### Pendientes para próxima sesión
- Verificar setup en máquina local (setup.ps1 + runserver)
- Cargar datos reales (CC, aeronaves, operadores)
- Probar document upload
- Revisar y ajustar templates si es necesario

## Sesión actual — 22 Julio 2026

### Avances
- Autenticación por token y contrato OpenAPI v1 publicados en el PR #1.
- Preflight de migraciones SQLite ejecutado correctamente.
- Backup SQLite de ensayo creado y verificado mediante manifiesto y checksum.
- Logs y respaldos runtime excluidos del repositorio.

### Decisión de persistencia
- SQLite continúa siendo la base local recomendada mientras el proyecto tenga un
  volumen moderado y un único entorno de trabajo.
- PostgreSQL se incorporará después, cuando exista más información real o antes
  del primer despliegue multiusuario. La migración se realizará mediante
  migraciones Django y backup/restore, sin copiar archivos internos de SQLite.
- No se expondrá la base SQLite local a Internet ni se reutilizarán credenciales
  locales en producción.

### Siguiente bloque
- Validar el archivo oficial de Capítulo 1 con `chapter1_import`.
- Aplicar la carga sólo después de revisar el informe de errores y duplicados.
- Mantener el ensayo real de PostgreSQL pendiente hasta disponer de servidor.

## Sesión actual — 23 Julio 2026

### Modernización UX/UI
- Se creó la rama `codex/ui-modernization` sobre la rama de estabilización.
- Se implementó una base visual semántica para modo claro y oscuro, con panel
  lateral contraíble y persistencia local.
- Se estableció español como idioma inicial y se mejoraron etiquetas,
  validaciones y controles de fecha/hora de los formularios.
- El Workboard incorporó navegación Tablero, Lista y Calendario, manteniendo
  HTMX y el drag-and-drop existente.
- Se añadió `GET /calendar/events/` para combinar permisos, mantenimiento y
  vencimientos Kanban respetando autenticación y acceso a tableros.
- Se añadió el Centro de administración operativo en `/administracion/`; el
  Django Admin continúa como administración técnica avanzada.
- Se creó la especificación OpenSpec en
  `openspec/changes/ui-modernization/`.

### Validación
- `manage.py check`: correcto.
- Ruff sobre aplicaciones, configuración y scripts: correcto.
- Suite completa: 116 pruebas correctas.
- `makemigrations --check --dry-run`: sin migraciones pendientes.
- `git diff --check`: correcto. Permanece sólo una advertencia local de acceso a
  `.pytest_cache`, sin impacto en la aplicación.

### Siguiente paso
- Revisar la aplicación levantada en modo claro/oscuro, cerrar hallazgos visuales
  de la revisión manual y abrir el PR de modernización desde esta rama.
