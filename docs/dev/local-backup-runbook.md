# Runbook de respaldo local

Estado: preparado; requiere localizar/confirmar la base SQLite y la carpeta de documentos reales.

## Objetivo

Mantener snapshots locales de la base SQLite y de los antecedentes privados sin subirlos a GitHub. Cada snapshot incluye un manifiesto SHA-256 y debe verificarse antes de considerarse válido.

## Primera ejecución manual

En PowerShell, elegir una carpeta de respaldo fuera de `D:\I+D\AeroControl` y fuera de `DOCUMENTS_ROOT`. Ejemplo:

```powershell
$env:AEROCONTROL_BACKUP_ROOT = 'D:\AeroControl-Backups'
.\scripts\backup-local.ps1
```

El script crea una carpeta `aerocontrol_YYYYMMDD_HHMMSS` con:

- copia de la base SQLite;
- carpeta `documents` con los antecedentes;
- `snapshot-manifest.json` con tamaños y hashes SHA-256.

## Verificación obligatoria

```powershell
.\scripts\verify-local-backup.ps1 -Snapshot 'D:\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS'
```

Solo un snapshot que termine con `Local snapshot verified` debe conservarse como respaldo válido.

## Programación semanal

Después de probar una ejecución manual, registrar la tarea de Windows:

```powershell
.\scripts\register-backup-task.ps1 `
  -DestinationRoot 'D:\AeroControl-Backups' `
  -DayOfWeek Sunday `
  -At '18:00'
```

La tarea se llama `AeroControl-LocalBackup`. Confirmar luego en el Programador de tareas que esté habilitada y revisar el primer resultado.

## Política mínima

- Mantener al menos tres snapshots verificados.
- No guardar el destino dentro del repositorio ni dentro de la carpeta de documentos fuente.
- No forzar restauraciones sobre una carpeta de trabajo existente.
- Probar restauración en una carpeta desechable:

```powershell
.\scripts\restore-local.ps1 `
  -Snapshot 'D:\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS' `
  -DestinationRoot 'D:\AeroControl-Restore-Test\YYYYMMDD'
```

## Criterio de cierre del bloque

- [ ] Confirmar la ruta real del medio externo.
- [ ] Confirmar que `DB_PATH` apunta a una base SQLite existente.
- [ ] Confirmar que `DOCUMENTS_DIR` existe y contiene los antecedentes privados.
- [ ] Ejecutar y verificar un snapshot manual.
- [ ] Registrar la tarea semanal.
- [ ] Conservar tres snapshots verificados.
- [ ] Completar una restauración de prueba y documentar el resultado.
