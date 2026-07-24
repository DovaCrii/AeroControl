# Plan de seguimiento: auditoría Impeccable

Fecha: 2026-07-24  
Estado: planificado, hooks automáticos desactivados

Este plan convierte la auditoría de `templates` y `static` en tareas ejecutables. Las correcciones se harán por lotes pequeños y se respaldarán mediante commits verificables.

## Orden recomendado

### Lote 1 — Claridad e internacionalización (P1)

- [ ] Revisar `templates/operations/flightrecord_detail.html` y localizar todos los textos visibles en inglés.
- [ ] Convertirlos a mensajes Django i18n (`{% translate %}` / `{% blocktranslate %}`).
- [ ] Añadir traducciones españolas al catálogo y compilar los archivos `.mo`.
- [ ] Verificar que el detector no encuentre textos visibles sin traducir.

Criterio de salida: el flujo de detalle/archivo de vuelo se muestra completamente en español y pasa `manage.py check`.

### Lote 2 — Tipografía y accesibilidad del login (P2)

- [ ] Revisar la jerarquía de títulos, etiquetas y mensajes en `templates/registration/login.html`.
- [ ] Mantener un único `h1`, asociar cada campo con su etiqueta y verificar foco visible.
- [ ] Sustituir colores inline o no tokenizados por variables del sistema de diseño cuando corresponda.

Criterio de salida: navegación por teclado funcional y contraste legible en tema claro y oscuro.

### Lote 3 — Layout responsive (P2)

- [ ] Validar el colapso del sidebar y la transición de ancho en `static/css/app.css:707`.
- [ ] Revisar tarjetas Kanban y confirmar que los bordes de estado son intencionales y tienen significado accesible.
- [ ] Probar anchos aproximados de 320, 768 y 1440 px, incluyendo zoom del 200 %.

Criterio de salida: no hay solapamientos ni scroll horizontal accidental; los estados Kanban no dependen solo del color.

### Lote 4 — Rendimiento y cierre (P3)

- [ ] Confirmar qué vistas usan Chart.js y HTMX.
- [ ] Cargar esas dependencias solo donde sean necesarias, si la medición demuestra beneficio.
- [ ] Ejecutar una nueva auditoría Impeccable y registrar comparación antes/después.

Criterio de salida: auditoría repetida, sin regresiones funcionales, con decisiones de optimización respaldadas por medición.

## Validación obligatoria por lote

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe scripts\compile_translations.py
node .agents\skills\impeccable\scripts\detect.mjs --json templates static
git diff --check
```

Después de cada lote:

```powershell
git status --short
git diff --stat
git add <archivos-del-lote>
git commit -m "ui: <descripcion breve del lote>"
git push
```

## Pendientes fuera de UI

- [ ] Registrar la tarea semanal de respaldo cuando se confirme la ruta del disco externo.
- [ ] Mantener tres snapshots verificados y documentar restauración.
- [ ] Resolver conflictos de operadores, centros de costo, habilitaciones DGAC y compatibilidad operador-aeronave únicamente con fuentes confirmadas.

## Regla de trabajo

No activar hooks de Impeccable todavía. Ejecutar la skill manualmente al inicio y al cierre de cada lote; si una corrección afecta datos o permisos, detener el lote y validar primero con pruebas funcionales.
