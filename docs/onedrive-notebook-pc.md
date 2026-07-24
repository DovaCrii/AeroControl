# Estrategia notebook–PC con OneDrive

## Decisión recomendada

Para una aplicación personal de un solo usuario, el notebook conserva la base
activa. OneDrive se usa como segunda copia de snapshots verificados, no como
ubicación de una SQLite que se abre y modifica desde dos equipos.

La ruta compartida propuesta es:

```text
D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups
```

La carpeta local de trabajo del PC puede ser:

```text
D:\I+D\AeroOpsDesk_Data-PC
```

El nombre `AeroOpsDesk_Data` identifica datos privados fuera del repositorio;
el código y el repositorio se llaman `AeroControl`.

## Por qué no usar la SQLite activa en OneDrive

SQLite puede generar archivos auxiliares (`-wal`, `-shm`) y OneDrive puede
sincronizar una versión mientras el proceso Django todavía la está escribiendo.
Eso puede provocar conflictos o una copia incompleta. Nunca se debe ejecutar la
misma base sincronizada simultáneamente en notebook y PC.

## Flujo de unificación

### 1. En el notebook, origen de datos

1. Detener Django y confirmar las variables `DB_PATH` y `DOCUMENTS_DIR` reales.
2. Crear un snapshot hacia OneDrive:

```powershell
$env:AEROCONTROL_BACKUP_ROOT = 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups'
.\scripts\backup-local.ps1
```

3. Verificar el snapshot y esperar a que OneDrive indique que terminó la
   sincronización.

### 2. En el PC, copia de trabajo

1. No abrir todavía la aplicación.
2. Verificar el snapshot desde OneDrive:

```powershell
.\scripts\verify-local-backup.ps1 `
  -Snapshot 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS'
```

3. Restaurar a una carpeta local de trabajo, nunca sobre una carpeta existente:

```powershell
.\scripts\restore-local.ps1 `
  -Snapshot 'D:\OneDrive - J.E.J. Ingeniería S.A\AeroControl-Backups\aerocontrol_YYYYMMDD_HHMMSS' `
  -DestinationRoot 'D:\I+D\AeroOpsDesk_Data-PC'
```

4. Crear el `.env` local del PC apuntando a esa carpeta y ejecutar Django.

## Regla de uso diario

- Un solo equipo abierto y escribiendo datos a la vez.
- Antes de cambiar de equipo: detener Django, crear y verificar snapshot.
- Esperar la sincronización completa de OneDrive.
- En el otro equipo: verificar el snapshot y restaurar en una carpeta limpia.
- No usar `-Force` sobre datos de trabajo sin una copia adicional.

## Estado actual

- OneDrive está disponible en `D:\OneDrive - J.E.J. Ingeniería S.A`.
- Snapshot `aerocontrol_20260724_112625` verificado y restaurado en el PC.
- La base fue restaurada y validada localmente; el contenido y los conteos de
  datos privados no se publican en GitHub.
- El `.env` local del PC apunta a `D:\I+D\AeroOpsDesk_Data-PC` y permanece
  ignorado por Git.
- La carpeta `documents` quedó disponible para restauración; si el notebook
  conserva antecedentes documentales, generar un nuevo snapshot después de
  confirmar que `DOCUMENTS_DIR` apunta a la carpeta correcta.
