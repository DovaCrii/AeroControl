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

## Objetivos abiertos

| Prioridad | Objetivo | Criterio de cierre |
| --- | --- | --- |
| P0 | Autorización por rol | Asignar los grupos estándar a usuarios reales y completar pruebas de 403 por módulo. |
| P1 | Archivos de cumplimiento | Validación de tipo por contenido/antimalware y política de retención. |
| P1 | Copias de seguridad | Backup consistente con manifiesto, checksum y restauración probada. |
| P2 | Dependencias front-end | Versiones fijadas con SRI u hospedadas localmente. |
| P2 | Observabilidad | Logs estructurados, health check y métrica de errores. |

Revisar esta lista en cada cambio de flujo, dependencia o despliegue.
