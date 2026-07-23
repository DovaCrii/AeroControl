# Especificación — Modernización UX/UI

## Sistema visual

- El documento HTML debe mantener sincronizados `data-theme` y `data-bs-theme`.
- Los controles deben exponer estados distinguibles de foco, hover, activo y
  deshabilitado en ambos temas.
- La navegación debe conservar una acción primaria visible por pantalla y
  agrupar las acciones secundarias.

## Internacionalización

- El idioma inicial debe ser español.
- Las etiquetas, validaciones, mensajes, estados y títulos de formularios deben
  poder traducirse mediante gettext.
- Los campos de fecha, hora y fecha-hora deben renderizar controles HTML
  específicos.

## Calendario

- `GET /calendar/events/` devuelve eventos autenticados dentro del rango
  solicitado.
- El feed acepta `start`, `end`, `types` y opcionalmente `board`.
- Cada evento incluye `id`, `type`, `title`, `start`, `allDay`, `color` y `url`.
- La respuesta debe respetar los límites de tenant y acceso al tablero.
- Debe existir una vista HTML de respaldo cuando JavaScript no esté disponible.

## Administración

- `/administracion/` muestra módulos operativos con descripción y permisos.
- La auditoría se presenta como solo lectura.
- `/admin/` se mantiene como administración técnica avanzada.
