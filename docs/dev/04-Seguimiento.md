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
- **Nombre**: AeroControl (repo: `DovaCrii/AeroControl`)
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

## Sesión actual — Carga Capítulo 1 vigente

### Resultado de la revisión
- Fuente: Capítulo 1 revisión 16, archivo oficial recibido el 23 de julio de 2026.
- Se extrajeron 14 aeronaves y 50 fichas permanentes de operadores RPA.
- Se incorporaron 11 centros de costo con responsable, fuera del repositorio de
  código y con trazabilidad en `ImportBatch`.
- Se cargaron 14 aeronaves y 41 operadores sin conflicto.
- Se consolidó un duplicado exacto y se dejaron cuatro grupos de RUT con datos
  contradictorios pendientes de confirmación.
- Ninguna aeronave ni operador se asignó a un CC por inferencia: la fuente no
  trae esa relación. El sistema los marca como pendientes de asignación.

### Brechas detectadas
- Falta una matriz oficial aeronave/persona → centro de costo.
- La fuente contiene duplicados y diferencias de nombre, dirección, teléfono,
  correo o habilitaciones para algunos RUT.
- Las habilitaciones aparecen como texto libre, sin fecha de emisión, vencimiento
  ni evidencia documental vinculada.
- Las aeronaves no traen año de fabricación ni fecha de vigencia operacional.
- El documento declara VLOS y ausencia de paracaídas, pero no modela aún la
  evidencia o el procedimiento que respalda cada condición.

### Mejoras recomendadas
- Crear una revisión de calidad antes de activar asignaciones: RUT, credencial
  DGAC, correo, teléfono y responsable de CC.
- Convertir habilitaciones y documentos DGAC en registros versionados con fecha
  de vencimiento y alertas.
- Añadir una matriz de compatibilidad operador–aeronave–habilitación antes de
  permitir permisos de vuelo.
- Incorporar al tablero una vista de pendientes de datos y un indicador de
  cobertura por CC, operador y aeronave.

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

## Sesión actual — continuidad backend y planificación — 24 julio 2026

### Decisiones consolidadas

- AeroControl continúa local-first para uso personal: Django, SQLite y
  documentos privados permanecen fuera del repositorio.
- OneDrive se usa como ubicación de snapshots verificados, no como ubicación de
  una SQLite activa compartida entre notebook y PC.
- Render Free y Supabase Free quedan limitados a pruebas sintéticas/anónimas;
  no son respaldo productivo de antecedentes privados.
- La CLI de Supabase queda disponible como herramienta opcional para un
  prototipo remoto, sin credenciales en GitHub.

### Evidencia registrada

- Snapshot `aerocontrol_20260724_112625` verificado desde OneDrive.
- Restauración realizada en `D:\I+D\AeroOpsDesk_Data-PC`.
- Tarea semanal `AeroControl-LocalBackup` registrada en el notebook.
- Seguimiento y comandos de observación centralizados en
  `docs/backend-follow-up.md`.
- La mejora de traducciones y workflow de planificación quedó respaldada en
  el commit `f1cd158`.

### Próximas tareas ordenadas

1. B-01: revisar historial de la tarea semanal y conservar tres snapshots
   verificados.
2. B-02: repetir el cambio notebook–PC con un snapshot nuevo.
3. B-03: confirmar documentos reales y completar restore drill documental.
4. B-04: resolver centros de costo y duplicados con fuente oficial.
5. B-05: modelar habilitaciones DGAC y compatibilidad operacional.
6. B-06: probar Supabase CLI sólo con datos sintéticos.
7. B-07: ejecutar ensayo PostgreSQL con rollback documentado.
