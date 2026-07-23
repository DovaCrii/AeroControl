# Diseño — Modernización UX/UI

La solución usa una capa de tokens CSS semánticos sobre el CSS actual y conserva
la renderización server-side. HTMX sigue manejando formularios modales, filtros
y actualizaciones parciales. FullCalendar se usa como mejora progresiva del
calendario; la cuadrícula server-side queda como respaldo.

El Workboard no crea una segunda fuente de datos: Tablero, Lista y Calendario
consumen `KanbanTask`. La fecha `due_date` es el evento de calendario de la
tarea en esta fase.

El centro administrativo compone enlaces y permisos de los módulos existentes;
no duplica modelos ni reglas de negocio. La administración Django permanece
disponible para tareas técnicas y modelos no expuestos operativamente.
