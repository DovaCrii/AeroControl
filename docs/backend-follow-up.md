# Seguimiento de backend, datos y respaldos

Fecha de actualización: 24 de julio de 2026  
Rama de trabajo: `codex/impeccable-ui-audit`

Este documento es la hoja de control para continuar el trabajo sin perder la
base de decisión ni la evidencia de respaldo. La aplicación es personal y
local-first: Django corre en el equipo activo, SQLite y documentos viven fuera
del repositorio y GitHub contiene sólo código, migraciones y documentación.

## Estado actual

| Control | Estado | Evidencia / ubicación |
| --- | --- | --- |
| Backend local Django + SQLite | Completo | `.env` local fuera de Git |
| Separación de código y datos | Completo | `D:\I+D\AeroOpsDesk_Data-PC` |
| Snapshot verificado | Completo | `D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_20260724_112625` |
| Restauración al PC | Completo | `D:\I+D\AeroOpsDesk_Data-PC` |
| Scripts de backup/verificación/restauración | Completo | `scripts/backup-local.ps1`, `scripts/verify-local-backup.ps1`, `scripts/restore-local.ps1` |
| Tarea semanal en notebook | Registrada | `AeroControl-LocalBackup` |
| Tres snapshots verificados | Pendiente | Revisar carpeta de respaldos |
| Restauración con documentos reales | Pendiente | El snapshot de referencia no contenía archivos documentales |
| Backend remoto con datos privados | No autorizado | Se mantiene fuera de Supabase/Render Free |

## Cómo observar los respaldos

### Revisar snapshots y manifiestos

```powershell
Get-ChildItem 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups' -Directory |
  Sort-Object Name -Descending

Get-Content 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS\snapshot-manifest.json'
```

### Verificar un snapshot antes de usarlo

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-local-backup.ps1 `
  -Snapshot 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS'
```

La salida válida es `Local snapshot verified`. Un error de hash, tamaño o
archivo faltante invalida el snapshot y debe detener la restauración.

### Revisar la tarea semanal

```powershell
Get-ScheduledTask -TaskName 'AeroControl-LocalBackup'
Get-ScheduledTaskInfo -TaskName 'AeroControl-LocalBackup'
```

Revisar especialmente `LastRunTime`, `LastTaskResult` y la existencia del
snapshot creado en la carpeta de OneDrive.

## Flujo seguro notebook → PC

1. En el equipo origen, detener Django y confirmar que no quedan procesos
   escribiendo SQLite.
2. Crear un snapshot fuera del repositorio y verificarlo.
3. Esperar que OneDrive termine de sincronizar la carpeta completa.
4. En el segundo equipo, verificar el snapshot y restaurarlo a una carpeta
   nueva; nunca restaurar sobre la carpeta activa.
5. Crear el `.env` local apuntando a la restauración y ejecutar migraciones y
   `scripts/verify.ps1`.
6. Trabajar en un solo equipo. Antes de cambiar de equipo, repetir el flujo.

La misma SQLite nunca debe abrirse simultáneamente en notebook y PC, y nunca
debe apuntarse `DB_PATH` directamente a una carpeta sincronizada por OneDrive.

## Backlog ordenado

- [ ] **B-01:** comprobar el historial de `AeroControl-LocalBackup` y generar
  snapshots hasta conservar tres verificaciones válidas.
- [ ] **B-02:** hacer una transferencia notebook → OneDrive → PC con snapshot
  nuevo y registrar el resultado sin publicar datos.
- [ ] **B-03:** confirmar la carpeta real de documentos en el notebook y
  ejecutar un restore drill que incluya archivos, si existen.
- [ ] **B-04:** cerrar duplicados y centros de costo sólo con fuente oficial;
  registrar cada decisión en el informe de calidad.
- [ ] **B-05:** modelar habilitaciones DGAC y compatibilidad
  operador–aeronave–habilitación con pruebas y permisos explícitos.
- [ ] **B-06:** preparar un proyecto Supabase/CLI con datos sintéticos y
  migraciones de prueba; no importar antecedentes privados.
- [ ] **B-07:** ejecutar ensayo PostgreSQL con backup previo, migración,
  checksum, smoke tests y rollback documentado.

## Registro de evidencias

| Fecha | Acción | Resultado | Evidencia |
| --- | --- | --- | --- |
| 2026-07-24 | Verificación del snapshot de referencia | Correcto | `aerocontrol_20260724_112625` |
| 2026-07-24 | Restauración al PC | Correcta | `D:\I+D\AeroOpsDesk_Data-PC` |
| 2026-07-24 | Pruebas de planificación y traducciones | 5 pruebas correctas | Commit `f1cd158` |

Completar esta tabla después de cada ejecución de respaldo o restauración.
