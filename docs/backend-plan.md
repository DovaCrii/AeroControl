# Plan de backend remoto — AeroControl

Última revisión: 24 de julio de 2026.

## Objetivo

Mantener el código en GitHub y alojar la aplicación, la base de datos y los
documentos fuera del repositorio. La primera instalación será un prototipo con
datos anonimizados; los antecedentes privados reales quedan bloqueados hasta
cumplir los criterios de producción definidos al final de este documento.

## Arquitectura aprobada para el prototipo

```text
PC del usuario
    │ HTTPS
    ▼
Render — Django + Gunicorn + WhiteNoise
    ├── PostgreSQL remoto mediante pooler TLS
    └── Supabase Storage — bucket privado S3
```

- Render ejecutará Django y publicará la interfaz mediante HTTPS.
- Supabase alojará PostgreSQL y el bucket privado `aerocontrol-documents`.
- Se conservará Django Auth; no se duplicará la autenticación con Supabase Auth.
- Habrá un único superusuario inicial y no habrá registro público.
- SQLite continuará disponible para desarrollo local y pruebas rápidas.

Render Free duerme tras 15 minutos sin tráfico y su sistema de archivos es
efímero. Supabase Free ofrece límites de 500 MB de base y 1 GB de archivos,
pausa proyectos después de una semana sin actividad y no incluye backups
automáticos. Por eso esta combinación es sólo para datos de prueba.

## Supabase CLI y control de cambios

La CLI oficial es parte del flujo operativo aunque no haya una skill de
Supabase instalada en Codex. La documentación de la CLI cubre `init`, `start`,
`link`, `migration`, `db diff`, `db push`, `db pull` y `db dump`.

Flujo obligatorio:

1. `supabase init` crea la configuración local fuera de los datos operativos.
2. `supabase link --project-ref <ref>` vincula el proyecto remoto y conserva
   credenciales en el almacén nativo cuando esté disponible.
3. Los cambios de esquema se prueban con `supabase db reset` y se revisan con
   `supabase migration list`.
4. Las migraciones Django siguen siendo la fuente de verdad para las tablas
   de `apps/*`; el despliegue de ese esquema se hace con `python manage.py
   migrate` contra PostgreSQL.
5. `supabase db push --dry-run` y luego `supabase db push` se reservan para
   objetos propios de Supabase, como configuración/políticas del bucket,
   extensiones o SQL de plataforma. No se mantendrá el mismo esquema de
   dominio en migraciones Django y `supabase/migrations`.
6. `supabase db dump --linked --data-only` genera backups fuera del repositorio.
7. `supabase storage ls --linked` y `supabase storage cp --recursive
   --linked` permiten inventariar y copiar el bucket durante respaldos; estas
   operaciones requieren la opción experimental de Storage cuando la CLI la
   indique.

Una vez iniciado este flujo no se harán cambios de esquema directamente en el
Dashboard de Supabase. El SQL propio de la plataforma vivirá en migraciones
revisables de Supabase; el dominio AeroControl seguirá siendo gestionado por
las migraciones Django y se validará contra PostgreSQL en CI.

## Cambios de aplicación

### Despliegue

- Añadir Gunicorn, WhiteNoise y una definición de Render (`render.yaml` o
  configuración equivalente).
- Configurar build con dependencias bloqueadas, compilación de traducciones,
  `collectstatic` y `check --deploy`.
- Ejecutar migraciones como paso predeploy y arrancar con
  `gunicorn config.wsgi:application`.
- Configurar `SECRET_KEY`, PostgreSQL, Storage, hosts permitidos y CSRF sólo
  como variables secretas del proveedor.
- Mantener el despliegue automático desde `main` condicionado a CI verde.

### Almacenamiento documental

- Introducir un servicio de almacenamiento con backend `local` para desarrollo
  y `s3` para Supabase Storage.
- Mantener `Document.file_path` como clave privada del objeto, no como URL.
- Adaptar carga, descarga, reemplazo y limpieza para el servicio, sin usar
  `Path(settings.DOCUMENTS_ROOT)` en producción.
- Descargar siempre a través de Django después de comprobar autenticación y
  permiso; el bucket nunca será público.
- Conservar archivado lógico y evitar borrado físico automático durante el
  prototipo.

### Salud, seguridad y operación

- Extender `/health/` para comprobar PostgreSQL y acceso al bucket sin revelar
  detalles internos.
- Añadir PostgreSQL como servicio de prueba en CI además de SQLite.
- Mantener logs sin cuerpos de petición, documentos, RUT, correos ni secretos.
- Añadir un script PowerShell local que ejecute `generate_alerts`, `supabase db
  dump`, inventario del Storage y comprobación de hashes.
- Guardar respaldos fuera del repositorio, con retención de 7 diarios y 4
  semanales; programar la tarea mediante Windows Task Scheduler.

## Carga inicial anonimizada

- Crear `export_anonymized_snapshot` e `import_anonymized_snapshot`.
- Exportar únicamente a una ruta fuera del repositorio y regenerar UUID.
- Mantener conteos, relaciones, estados y orden temporal, pero desplazar fechas.
- Sustituir nombres, RUT, correos, teléfonos, direcciones, credenciales DGAC,
  matrículas, series, responsables, ubicaciones, propósitos, notas y textos
  libres por valores sintéticos deterministas.
- Excluir usuarios, tokens, sesiones, `AuditEvent` e `ImportBatch`.
- No copiar documentos reales; crear archivos sintéticos para probar PDF, DOCX,
  XLSX e imágenes.
- Generar manifiesto con conteos, hashes y búsqueda de valores originales antes
  de importar al proyecto Supabase.

## Validación y aceptación

- `check --deploy`, migraciones, Ruff, Bandit, `pip-audit` y suite completa
  verdes en CI.
- Login, permisos, CRUD, calendario, Kanban, alertas y exportaciones funcionan
  sobre PostgreSQL.
- Carga, descarga, reemplazo, archivado y rechazo de documentos funcionan en
  el bucket privado.
- Reiniciar Render no elimina datos ni documentos.
- La copia anonimizada conserva conteos y relaciones, sin identificadores reales.
- Un backup restaurado en un proyecto temporal recupera base y Storage.
- `git ls-files` no contiene SQLite, documentos, dumps, backups, `.env` ni
  secretos.

## Criterio para datos privados reales

No se cargarán antecedentes reales en el plan gratuito. Antes se requiere,
como mínimo:

- Servicio web y base sin suspensión por inactividad.
- Backups automáticos y ensayo documentado de restauración.
- MFA para la administración.
- Revisión de residencia, retención y tratamiento de datos.
- Antivirus operativo para documentos.
- Rotación de secretos, monitoreo y revisión periódica de accesos.

## Referencias operativas

- [Supabase CLI](https://supabase.com/docs/reference/cli/introduction)
- [Migraciones de base con Supabase](https://supabase.com/docs/guides/deployment/database-migrations)
- [Backups con Supabase CLI](https://supabase.com/docs/guides/platform/backups)
- [Compatibilidad S3 de Storage](https://supabase.com/docs/guides/storage/s3/compatibility)
- [Limitaciones de Render Free](https://render.com/docs/free)
