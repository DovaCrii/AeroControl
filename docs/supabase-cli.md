# Operación de Supabase CLI

La CLI es una herramienta operativa para administrar el proyecto remoto sin
poner credenciales ni datos en GitHub. No hay una skill de Supabase instalada
en el entorno Codex actual; se usa la CLI oficial siguiendo este runbook.

## Instalación y enlace

Instala la CLI según la documentación oficial y verifica:

```powershell
supabase --version
supabase login
supabase link --project-ref <project-ref>
```

El token de `supabase login` debe quedar en el almacén de credenciales del
usuario o en la variable de entorno de CI. Nunca se guarda en el repositorio.

## Regla de migraciones

Las migraciones Django son la fuente de verdad para las tablas de AeroControl:

```powershell
uv run python manage.py migrate
```

Las migraciones Supabase sólo administran objetos propios de la plataforma,
como políticas/configuración del bucket o extensiones. Antes de aplicar una de
ellas:

```powershell
supabase db diff --linked
supabase db push --linked --dry-run
supabase db push --linked
supabase migration list --linked
```

No se deben editar tablas de dominio desde el Dashboard una vez iniciado el
flujo de migraciones.

## Backup y Storage

Configura `AEROCONTROL_BACKUP_DIR` y `SUPABASE_STORAGE_BUCKET` en el entorno del
usuario, ambos fuera del repositorio, y ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\supabase-backup.ps1
```

El script produce `schema.sql`, `data.sql`, el inventario de migraciones, una
copia del bucket y un manifiesto SHA-256. La carpeta de salida debe respaldarse
en un disco protegido y probarse en un proyecto Supabase temporal.

Comandos de inventario y copia manual:

```powershell
supabase storage ls --linked --recursive --experimental
supabase storage cp --linked --recursive --experimental `
  "ss://<bucket>" "D:\AeroControl-Backups\storage"
```

Los objetos del bucket son privados y la aplicación sólo los entrega después
de autorizar la descarga.
