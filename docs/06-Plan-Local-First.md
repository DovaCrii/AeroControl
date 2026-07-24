---
tags: [aero-ops, plan, local-first]
---

# Plan de seguimiento: backend local-first

## Decision adoptada — 24 julio 2026

AeroControl se mantiene como una aplicacion personal local. El backend Django,
la base de datos y los documentos privados viven fuera del repositorio en el
notebook. GitHub no contiene antecedentes, bases SQLite, documentos ni
secretos.

El mismo modelo se aplicó al PC: se restauró una copia verificada desde
OneDrive a `D:\I+D\AeroOpsDesk_Data-PC`. El equipo activo se elige por sesión;
la SQLite no se abre desde dos equipos al mismo tiempo.

## Hitos

- [x] Documentar la arquitectura local y los limites de los planes gratuitos.
- [x] Incorporar `scripts/backup-local.ps1` para copiar base y documentos.
- [x] Incorporar `scripts/verify-local-backup.ps1` para comprobar hashes.
- [x] Incorporar `scripts/restore-local.ps1` para restaurar a una carpeta
      desechable sin tocar la base de trabajo.
- [x] Ejecutar restore drill con una base y carpeta temporales sintéticas;
      resultado: SQLite y documentos restaurados y verificados.
- [x] Preparar `scripts/register-backup-task.ps1` para programar el backup
      semanal sin guardar la ruta de datos en Git.
- [x] Registrar la tarea semanal en el notebook con el nombre
      `AeroControl-LocalBackup`.
- [x] Unificar notebook y PC mediante el snapshot verificado
      `aerocontrol_20260724_112625` en OneDrive, sin abrir la misma SQLite
      simultáneamente en ambos equipos.
- [ ] Conservar tres snapshots verificados en medios separados.
- [ ] Confirmar la carpeta documental real del notebook y completar un restore
      drill que incluya archivos, si existen.
- [ ] Publicar unicamente un snapshot anonimizado en Supabase/Render para
      pruebas remotas.
- [ ] Evaluar PostgreSQL y hosting pagado solo si aparece una necesidad de
      acceso remoto, varios usuarios o disponibilidad continua.

## Criterio de avance

Un hito se considera completo cuando existe evidencia reproducible: comando
ejecutado, resultado guardado fuera del repositorio y una prueba de restauracion
exitosa. No se cargaran datos privados reales en servicios gratuitos antes de
completar el restore drill y definir controles de acceso y retencion.

## Seguimiento operativo

La revisión observable de snapshots, la tarea semanal, el cambio seguro entre
notebook y PC y el backlog B-01…B-07 están en `docs/backend-follow-up.md`.
Después de cada respaldo se debe actualizar su tabla de evidencias y crear un
commit pequeño en la rama de trabajo.

## Referencias

- `docs/backend-plan.md`: arquitectura y secuencia de ambientes.
- `docs/local-backup-runbook.md`: procedimiento operativo de backup y restauracion.
- `docs/04-Seguimiento.md`: decisiones historicas y pendientes de datos.
