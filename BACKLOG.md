# Backlog — AeroControl

Última revisión: 22 de julio de 2026. Este documento separa lo entregado de los
objetivos que aún requieren trabajo para evitar duplicar iniciativas cerradas.

## Entregado en la estabilización inicial

- [x] Flujo de permisos de vuelo y bitácora de vuelos con validaciones de
  aeronave, operador, fecha y horas.
- [x] Calendario de operaciones y mantenimientos; historial de cambios de
  estado en mantenimiento.
- [x] Kanban con arrastrar y soltar, prioridades, asignación a operadores y
  filtros.
- [x] Dashboard con gráficos y exportación CSV segura.
- [x] Tema oscuro, iconografía semántica, marca AeroControl e interfaz base
  bilingüe (ES/EN).
- [x] Roles estándar, permisos en operaciones mutantes, validación explícita de
  formularios y controles de seguridad documentados.
- [x] Entorno reproducible con `uv`, pruebas, Ruff, Bandit, pip-audit, CI y
  Dependabot.

## Próxima etapa — cierre funcional y de calidad (P0)

- [ ] Corregir la deriva de `PermissionHistory`: alinear modelo y migración,
  validar una transición completa y confirmar rollback si falla el historial.
- [ ] Completar la traducción ES/EN de vistas, formularios, mensajes y
  validaciones restantes; añadir pruebas para ambos idiomas.
- [ ] Asignar los grupos estándar a usuarios reales y probar respuestas 403 en
  cada módulo con operaciones de escritura.
- [ ] Aumentar pruebas de regresión para cargas de documentos, archivado,
  transiciones de estado y restauración de respaldos.
- [ ] Revisar accesibilidad de teclado, foco, contraste y comportamiento en
  pantallas pequeñas de los flujos críticos.

## Fase 4 — Importación, búsquedas y reportes (P1)

- [ ] Importación Excel validada, con vista previa, reporte de errores y
  operación reversible.
- [ ] Carga normalizada del Capítulo 1 con mapeos versionados.
- [ ] Búsqueda global con permisos y filtros por dominio.
- [ ] Reportes Word y Excel exportables con plantillas controladas.
- [ ] Validaciones cruzadas entre seguro, aeronave, operador, permiso y
  habilitación.

## Operación segura y confiable (P1)

- [ ] Cerrar autorización de lectura y exportación: definir el alcance del rol
  Viewer y exigir permisos `view_*`/exportación donde corresponda.
- [ ] Validar `DocumentType.code`, normalizar nombres y verificar la ruta antes
  de escribir para impedir traversal; después sumar tipo de contenido,
  análisis antimalware y política de retención.
- [ ] Implementar respaldo con manifiesto, checksum y prueba automatizada de
  restauración.
- [ ] Añadir health check, logs estructurados y métricas de errores.
- [ ] Fijar dependencias front-end con SRI o servirlas localmente y definir
  Content Security Policy.
- [ ] Registrar auditoría de acciones administrativas y cambios de estado.

## Evolución para escalar (P2)

- [ ] Diseñar API v1 con Django REST Framework, autenticación y contratos
  versionados.
- [ ] Evaluar PostgreSQL y migración con plan de respaldo/rollback antes de
  cualquier despliegue multiusuario.
- [ ] Incorporar permisos por objeto, tenancy si aplica y una estrategia de
  concurrencia.
- [ ] Separar frontend sólo cuando las necesidades de API, offline o móvil lo
  justifiquen; mantener el monolito Django mientras reduzca complejidad.
- [ ] Definir pipeline de entrega: entorno staging, migraciones, backup previo,
  verificación y rollback.
