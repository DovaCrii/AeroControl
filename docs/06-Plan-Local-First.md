---
tags: [aero-ops, plan, local-first]
---

# Plan de seguimiento: backend local-first

## Decision adoptada — 24 julio 2026

AeroControl se mantiene como una aplicacion personal local. El backend Django,
la base de datos y los documentos privados viven fuera del repositorio en el
notebook. GitHub no contiene antecedentes, bases SQLite, documentos ni
secretos.

## Hitos

- [x] Documentar la arquitectura local y los limites de los planes gratuitos.
- [x] Incorporar `scripts/backup-local.ps1` para copiar base y documentos.
- [x] Incorporar `scripts/verify-local-backup.ps1` para comprobar hashes.
- [x] Incorporar `scripts/restore-local.ps1` para restaurar a una carpeta
      desechable sin tocar la base de trabajo.
- [x] Ejecutar restore drill con una base y carpeta temporales sintéticas;
      resultado: SQLite y documentos restaurados y verificados.
- [ ] Programar el backup semanal en Windows Task Scheduler.
- [ ] Conservar tres snapshots verificados en medios separados.
- [ ] Publicar unicamente un snapshot anonimizado en Supabase/Render para
      pruebas remotas.
- [ ] Evaluar PostgreSQL y hosting pagado solo si aparece una necesidad de
      acceso remoto, varios usuarios o disponibilidad continua.

## Criterio de avance

Un hito se considera completo cuando existe evidencia reproducible: comando
ejecutado, resultado guardado fuera del repositorio y una prueba de restauracion
exitosa. No se cargaran datos privados reales en servicios gratuitos antes de
completar el restore drill y definir controles de acceso y retencion.

## Referencias

- `docs/backend-plan.md`: arquitectura y secuencia de ambientes.
- `docs/local-backup.md`: procedimiento operativo de backup y restauracion.
- `docs/04-Seguimiento.md`: decisiones historicas y pendientes de datos.
