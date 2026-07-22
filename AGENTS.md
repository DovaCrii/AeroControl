# AeroControl — guía para Codex

## Objetivo

Aplicación Django local-first para coordinar operaciones de aviación. La seguridad, trazabilidad y consistencia de datos prevalecen sobre cambios cosméticos.

## Flujo de trabajo

- Trabaja en ramas `codex/<area>`; no modifiques `main` directamente.
- Usa `uv sync --all-groups` y ejecuta `scripts/verify.ps1` antes de entregar cambios.
- Define `DB_PATH`, `DOCUMENTS_DIR` y `LOGS_DIR` fuera del repositorio. Nunca confirmes datos operativos, documentos ni secretos.
- Para cambios de modelo, crea y revisa migraciones; incluye pruebas de regresión.
- Conserva la interfaz desktop-first, accesible por teclado y en español de Chile cuando se modifiquen textos de producto.

## Controles obligatorios

- No uses `fields = "__all__"` en formularios de escritura.
- Las transiciones de estado, archivos, exportaciones y archivado requieren permisos explícitos.
- Valida relaciones de dominio en formularios/modelos, no solo en la interfaz.
- No interpolar JSON controlado por usuarios con `|safe`; usa `json_script`.
- Las exportaciones CSV deben neutralizar fórmulas y limitar campos a datos aprobados.

## Referencias

- Arquitectura: `ARCHITECTURE.md`
- Backlog: `BACKLOG.md`
- Puesta en marcha: `README.md` y `scripts/setup.ps1`
