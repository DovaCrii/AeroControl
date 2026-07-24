# Plan de seguimiento: auditoría Impeccable

Fecha: 2026-07-24  
Estado: planificado, hooks automáticos desactivados

Este plan convierte la auditoría de `templates` y `static` en tareas ejecutables. Las correcciones se harán por lotes pequeños y se respaldarán mediante commits verificables.

## Orden recomendado

### Lote 1 — Claridad e internacionalización (P1)

- [x] Revisar `templates/operations/flightrecord_detail.html` y localizar todos los textos visibles en inglés.
- [x] Convertirlos a mensajes Django i18n (`{% translate %}` / `{% blocktranslate %}`).
- [x] Añadir traducciones españolas al catálogo y compilar los archivos `.mo`.
- [x] Verificar que el detector no encuentre textos visibles sin traducir.

Criterio de salida: el flujo de detalle/archivo de vuelo se muestra completamente en español y pasa `manage.py check`.

### Lote 2 — Tipografía y accesibilidad del login (P2)

- [x] Revisar la jerarquía de títulos, etiquetas y mensajes en `templates/registration/login.html`.
- [x] Mantener un único `h1`, asociar cada campo con su etiqueta y verificar foco visible.
- [x] Sustituir colores inline o no tokenizados por variables del sistema de diseño cuando corresponda.

Criterio de salida: navegación por teclado funcional y contraste legible en tema claro y oscuro.

### Lote 3 — Layout responsive (P2)

- [x] Validar el colapso del sidebar y la transición de ancho en `static/css/app.css:707`.
- [x] Revisar tarjetas Kanban y confirmar que los bordes de estado son intencionales y tienen significado accesible.
- [x] Probar reglas responsive para anchos aproximados de 320, 768 y 1440 px, incluyendo overflow táctil controlado.

Criterio de salida: no hay solapamientos ni scroll horizontal accidental; los estados Kanban no dependen solo del color.

### Lote 4 — Rendimiento y cierre (P3)

- [x] Confirmar qué vistas usan Chart.js y HTMX.
- [x] Cargar Chart.js solo en dashboard; mantener HTMX global porque lo usan múltiples vistas.
- [x] Ejecutar una nueva auditoría Impeccable y registrar comparación antes/después.

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

## Bloque siguiente — respaldo local

El procedimiento quedó documentado en `docs/local-backup-runbook.md`. El
destino `D:\AeroControl-Backups` ya fue reservado, pero la ejecución está
bloqueada porque la ruta configurada de la base SQLite no existe en este equipo.

- [ ] Confirmar el destino real del backup.
- [ ] Confirmar `DB_PATH` y `DOCUMENTS_DIR` reales con datos locales.
- [ ] Ejecutar y verificar un snapshot manual.
- [ ] Registrar la tarea semanal de Windows.
- [ ] Conservar tres snapshots verificados.
- [ ] Probar una restauración en carpeta desechable.

## Regla de trabajo

No activar hooks de Impeccable todavía. Ejecutar la skill manualmente al inicio y al cierre de cada lote; si una corrección afecta datos o permisos, detener el lote y validar primero con pruebas funcionales.

## Revisión de cierre de los cinco entregables

- [x] Auditoría inicial registrada en `docs/impeccable-audit.md`.
- [x] Plan de seguimiento registrado en este documento.
- [x] Lote 1 respaldado en `dfbf968`.
- [x] Lote 2 respaldado en `7a283e0`.
- [x] Lote 3 respaldado en `3db3d45`.
- [x] Lote 4 y auditoría final completados; detector final: 3 avisos intencionales de bordes Kanban.
