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
- [x] Listas y formularios compartidos del registro traducidos, con
  confirmación visible tras guardar y accesos operativos desde el panel.
- [x] Flujo de documentos revisado en navegador: creación abre correctamente,
  selector de entidad/registro depende del tipo elegido, cancelar cierra el
  modal y los filtros conservan su estado.
- [x] Roles estándar, permisos en operaciones mutantes, validación explícita de
  formularios y controles de seguridad documentados.
- [x] Entorno reproducible con `uv`, pruebas, Ruff, Bandit, pip-audit, CI y
  Dependabot.

## Próxima etapa — cierre funcional y de calidad (P0)

- [x] Corregir la deriva de `PermissionHistory`: modelo y migraciones alineados,
  transiciones atómicas y prueba de actor, estados y notas del historial.
- [x] Completar la traducción ES/EN de los flujos específicos de alertas,
  mantenimiento, calendario y Kanban; añadir pruebas de regresión para los
  estados, filtros y acciones visibles.
- [x] Asignar los grupos estándar a usuarios reales y probar respuestas 403 en
  cada módulo con operaciones de escritura.
- [ ] Aumentar pruebas de regresión para cargas de documentos, archivado,
  transiciones de estado y restauración de respaldos.
- [x] Revisar accesibilidad de teclado, foco, contraste y comportamiento en
  pantallas pequeñas de los flujos críticos.
- [x] Convertir los gráficos vacíos del panel en un estado inicial guiado:
  explicar el orden de carga y enlazar a Centro de costo, aeronave, operador y
  permiso.
- [x] Añadir navegación lateral colapsable en pantallas pequeñas, con control
  de teclado y foco gestionado.

## Fase 4 — Importación, búsquedas y reportes (P1)

- [ ] Importación Excel validada, con vista previa, reporte de errores y
  operación reversible.
- [ ] Carga normalizada del Capítulo 1 con mapeos versionados.
- [ ] Búsqueda global con permisos y filtros por dominio.
- [ ] Reportes Word y Excel exportables con plantillas controladas.
- [ ] Validaciones cruzadas entre seguro, aeronave, operador, permiso y
  habilitación.

## Operación segura y confiable (P1)

- [x] Cerrar autorización de lectura y exportación: los listados y CSV exigen
  permisos `view_*`; las altas, cambios, archivado y transiciones mantienen sus
  permisos mutantes y pruebas `403`.
- [x] Validar `DocumentType.code`, normalizar nombres y verificar la ruta antes
  de escribir para impedir traversal; validar extensión, firma de archivo y
  límite de tamaño.
- [x] Añadir punto de integración antimalware configurable y comando de
  retención en modo simulación/ejecución para documentos.
- [x] Implementar respaldo con manifiesto, checksum y comando de verificación.
- [x] Añadir prueba automatizada de restauración en un destino aislado.
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
