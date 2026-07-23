# Backlog — AeroControl

Última revisión: 23 de julio de 2026. Este documento separa lo entregado de los
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

## Modernización UX/UI — rama `codex/ui-modernization`

- [x] Aplicar sistema visual semántico para modo claro/oscuro y botones con
  estados visibles.
- [x] Establecer español como idioma inicial y completar etiquetas operativas
  de formularios con controles de fecha/hora.
- [x] Añadir panel lateral contraíble en escritorio con persistencia local.
- [x] Añadir calendario unificado de permisos, mantenimiento y tareas Kanban.
- [x] Añadir vistas Tablero, Lista y Calendario al Workboard.
- [x] Añadir Centro de administración operativo separado del Django Admin.
- [ ] Verificar visualmente las superficies en escritorio, móvil, teclado y
  modo oscuro; completar ajustes derivados de la revisión.
- [ ] Cerrar la rama mediante commit, push y PR después de la suite completa.

- [x] Corregir la deriva de `PermissionHistory`: modelo y migraciones alineados,
  transiciones atómicas y prueba de actor, estados y notas del historial.
- [x] Completar la traducción ES/EN de los flujos específicos de alertas,
  mantenimiento, calendario y Kanban; añadir pruebas de regresión para los
  estados, filtros y acciones visibles.
- [x] Asignar los grupos estándar a usuarios reales y probar respuestas 403 en
  cada módulo con operaciones de escritura.
- [x] Aumentar pruebas de regresión para cargas de documentos, archivado,
  transiciones de estado y restauración de respaldos.
- [x] Revisar accesibilidad de teclado, foco, contraste y comportamiento en
  pantallas pequeñas de los flujos críticos.
- [x] Convertir los gráficos vacíos del panel en un estado inicial guiado:
  explicar el orden de carga y enlazar a Centro de costo, aeronave, operador y
  permiso.
- [x] Añadir navegación lateral colapsable en pantallas pequeñas, con control
  de teclado y foco gestionado.

## Bloque Kanban operativo — Notion híbrido

- [x] Añadir tipos de etapa operativos y conservar etapas antiguas como
  personalizadas.
- [x] Etiquetas configurables por tablero con color, orden y archivado lógico.
- [x] Checklist ordenado por tarea y avance calculado automáticamente.
- [x] Panel lateral para consultar/editar tareas y alta rápida existente por
  columna.
- [x] Vista de lista con búsqueda, filtros por estado/etiqueta/prioridad/
  responsable y ordenación; filtros persistidos en URL.
- [x] Acciones de archivado reversible y drag-and-drop desactivado cuando hay
  filtros incompatibles.
- [x] Regresión automatizada para detalle, checklist, avance y filtros.

## Fase 4 — Importación, búsquedas y reportes (P1)

- [x] Importación CSV validada de Centros de costo, con vista previa, reporte
  de errores, operación transaccional y reversión lógica por lote.
- [x] Extender el mismo flujo a aeronaves, validando matrícula y centro de
  costo antes de aplicar el lote.
- [x] Extender el mismo flujo a operadores, validando identificador de empleado
  y centro de costo antes de aplicar el lote.
- [x] Definir mapping canónico versionado chapter1-v1 para centros de costo,
  aeronaves y operadores.
- [x] Preparar cargador transaccional chapter1_import con validación de esquema,
  duplicados y referencias; queda pendiente ejecutarlo con la fuente oficial.
- [x] Añadir adaptador Excel con hojas y encabezados canónicos versionados.
- [x] Búsqueda global con permisos de lectura por dominio y enlaces directos a
  los módulos operativos.
- [x] Reporte CSV operativo de tareas Kanban reutilizando filtros y columnas de
  la vista de lista; compatible con Excel.
- [x] Reporte XLSX nativo de tareas Kanban con hoja congelada, filtro y
  columnas dimensionadas.
- [x] Reporte Word operativo de tareas Kanban con plantilla controlada y filtros
  aplicados.
- [x] Validaciones cruzadas base de aeronave, operador, centro de costo y
  asignación, permisos de vuelo y bitácoras mediante comando de calidad de
  datos.
- [ ] Completar validaciones cruzadas de seguro, permiso y habilitación cuando
  esos dominios tengan sus fuentes normalizadas.

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
- [x] Añadir health check de dependencias (/health/) para base de datos y
  almacenamiento documental.
- [x] Añadir correlación X-Request-ID y eventos JSON con método, ruta, estado y
  duración para observabilidad básica.
- [x] Definir Content-Security-Policy-Report-Only configurable para validar
  fuentes externas sin romper la interfaz existente.
- [x] Fijar SortableJS a una versión exacta con SRI y crossorigin.
- [x] Registrar acciones mutantes autenticadas con actor, solicitud, resultado
  y correlación; consultar el historial desde Django Admin.
- [x] Hacer el historial de auditoría inmutable desde Django Admin.

## Evolución para escalar (P2)

- [x] Exponer contrato inicial API v1 de lectura para tareas Kanban con
  permisos, filtros y paginación.
- [x] Añadir PATCH API v1 para actualizar tareas con validación de campos,
  prioridad, etapa y permisos de modificación.
- [x] Añadir índice JSON autodocumentado en /api/v1/ con endpoints, permisos y
  límites de paginación.
- [x] Añadir comando scale_readiness y runbook de PostgreSQL con respaldo,
  reconciliación y rollback explícitos.
- [x] Incorporar Django REST Framework con endpoint read-only versionado para
  tareas Kanban y permisos de modelo.
- [x] Completar autenticación por token y documentación OpenAPI para API v1.
- [x] Parametrizar backend PostgreSQL opcional con psycopg y mantener SQLite como
  valor por defecto.
- [ ] Ejecutar ensayo real de migración PostgreSQL con respaldo/rollback antes
  de cualquier despliegue multiusuario.
- [x] Incorporar permisos por objeto para tableros Kanban con roles viewer,
  editor y manager.
- [x] Añadir base de tenancy opcional con OperationalTenant y membresías;
  tableros actuales sin tenant siguen siendo compartidos.
- [x] Añadir control de concurrencia optimista en PATCH API mediante
  If-Unmodified-Since y respuesta 409 ante conflictos.
- [x] Evaluar la frontera frontend y documentar criterios; mantener el
  monolito Django mientras reduzca complejidad.
- [x] Definir preflight CI de staging con migraciones, health/readiness, backup
  previo y verificación de checksum; el despliegue productivo sigue siendo
  manual y reversible.

## Fases pendientes de estabilización

- [x] Unificar el alcance de tenant y acceso de tablero en HTML, HTMX,
  exportaciones, búsqueda y API; evidencia: pruebas Workboard y DRF.
- [x] Completar contexto de objeto en `AuditEvent` y hacer tolerante el fallo de
  escritura del registro; evidencia: pruebas de auditoría.
- [x] Consolidar toda la escritura de tareas en el ViewSet/servicio DRF único,
  preservando el contrato `/api/v1/`; depende de cerrar la matriz de clientes.
- [x] Extraer selectores y el parser CSV común, incluyendo límite de 500 filas,
  precarga de referencias y reversión atómica.
- [x] Añadir FKs de actor compatibles y tenant nullable en el dominio raíz,
  incluyendo migraciones y reporte de etiquetas no resueltas.
- [x] Activar rotación de logs y declarar `uv.lock`/`pyproject.toml` como fuente
  única de dependencias.
- [ ] Tenancy estricto, PostgreSQL, DJI, Celery/Redis, vínculo `Operator.user`
  y frontend separado permanecen diferidos hasta cumplir sus criterios de
  entrada.
