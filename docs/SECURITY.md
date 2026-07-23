# Seguridad y estabilidad

## Controles incorporados

- Dependencias bloqueadas en `uv.lock`, auditoría con `pip-audit` y análisis estático con Bandit en CI.
- Formularios de escritura con listas explícitas de campos; los metadatos de auditoría y estados no se aceptan desde el navegador.
- Las exportaciones CSV excluyen metadatos/notas y neutralizan fórmulas de hoja de cálculo.
- El dashboard serializa datos con `json_script`; no usa HTML seguro para datos de negocio.
- El cierre de sesión es `POST` con CSRF.
- Los documentos se limitan a entidades de negocio permitidas y existentes; su ruta se verifica antes de descargar.
- Los roles estándar se crean con `python manage.py bootstrap_roles`; las operaciones mutantes requieren permisos de Django.
- Los secretos de producción no tienen valor por defecto y se activaron validadores de contraseña.

## Estado de los objetivos históricos

Los objetivos definidos durante la estabilización inicial fueron cerrados en
el commit de estabilización actual. El trabajo futuro de seguridad y
operación debe registrarse en `BACKLOG.md` para evitar duplicar tareas
históricas.

| Prioridad | Objetivo | Estado | Evidencia |
| --- | --- | --- |
| P0 | Historial de permisos | Cerrado | Modelo, migraciones, transiciones y pruebas en `apps/operations/`. |
| P1 | Autorización de lectura/exportación | Cerrado | Permisos `view_*`, exportaciones autorizadas y pruebas `403`. |
| P1 | Archivos de cumplimiento | Cerrado | Validación de ruta, firma, tamaño, antimalware configurable y retención. |
| P1 | Copias de seguridad | Cerrado | Manifiesto, checksum, verificación y restauración probada. |
| P2 | Dependencias front-end | Cerrado | Versiones fijadas, SRI y CSP report-only documentada. |
| P2 | Observabilidad | Cerrado | Logs estructurados, `X-Request-ID` y `/health/`. |

Revisar esta lista en cada cambio de flujo, dependencia o despliegue.
