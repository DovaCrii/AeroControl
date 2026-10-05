# Despliegue a la VM `p340`

Reglas verificadas (de `AGENTS.md`). Los comandos exactos y rutas están en `docs/dev/remote-vm-operations.md` y `docs/dev/ubuntu-vm-deploy.md`; este archivo dice **qué comprobar y qué no hacer**. Desplegar solo cuando el usuario lo pida.

## Dónde corre cada cosa
- Merge y push: en **Windows** (las ramas solo existen ahí).
- Despliegue: **dentro** de la sesión SSH de la VM. `/opt/aerocontrol` es ruta Linux; en PowerShell se resolvería como `C:\opt\...`.

## Antes de dictar los comandos
1. Comparar `git log --oneline -1` de la VM con lo que se va a subir. **El despliegue es el de TODO lo que falta en la VM, no el del último commit**: unir los pasos de todas las filas intermedias. El 2026-08-31 se entregó "solo `collectstatic`" sobre una VM que no había corrido una migración anterior y toda página que armaba el panel murió con `no such column`. Si la tanda necesita `migrate`, el comando va **en el bloque**, no en una nota al final.
2. Primer comando de todo despliegue: `git status --short --branch`. La primera línea debe decir `## main...origin/main`, **no** `## HEAD (no branch)`.
3. Tras un rollback (`git checkout <commit>`) la VM queda en HEAD desprendido y `git pull` no despliega nada, pero `uv sync`, `collectstatic` y el reinicio **corren igual sobre el código viejo sin error**. Volver con `git checkout main` el mismo día del rollback.
4. Si se va a versionar un archivo que ya existe **sin versionar** en la VM, apartarlo allá primero (`mv` a `~`, no `rm`; comparar con `diff` después). Si no, `git pull` se niega y el resto del bloque corre sobre código viejo con respuestas plausibles.

## Cómo ejecutarlo
- **Cargar el entorno primero y con `set -a`**: `set -a; source /etc/aerocontrol.env; set +a`. Sin `set -a` se definen variables de shell, no de entorno, y `manage.py` cae a `config.settings.dev`. Sin entorno, `collectstatic` muere con `SECRET_KEY not found`. Verificar con `echo` `DJANGO_SETTINGS_MODULE` y `DB_PATH` **antes** de migrar.
- **Pegar por pasos**, mirando la salida de cada uno. No encadenar en una línea: los `;` que exige la carga del entorno cortan la cadena `&&`, y un `git pull` fallado no frena el `restart`.
- `collectstatic` es obligatorio en producción (estáticos con hash; sin `staticfiles.json` toda etiqueta `{% static %}` falla). `build.sh` ya lo ejecuta.
- No hace falta `compilemessages`: el `.mo` está versionado.

## Cómo saber que llegó
- **El hash final de `git log --oneline -1` en la VM debe coincidir con el `main` empujado.** Es la única prueba.
- Las tres señales de un despliegue que no llegó: `[behind N]` en el `status`, `uv sync` sin instalar nada y `migrate` sin aplicar nada.
- Un 500 después de desplegar: `uv run python manage.py showmigrations <app> | tail -6`. Una migración sin `[X]` con código nuevo que ya la usa lo explica sin leer el traceback.
- Si se agregó una función que notifica: comprobar el camino real (`--dry-run`, `systemctl list-timers`), no solo los tests.

## Cosas que nunca se despliegan encendidas
- Service worker: detrás de `SERVICE_WORKER_ENABLED=False` (ver `lecciones.md`; postmortem en `docs/dev/postmortem-2026-09-08-service-worker.md`).
- Trabajos programados nuevos: registrar el timer y comprobar que aparece en `list-timers`.

## Higiene
- No teclear credenciales como comando en la terminal de la VM. Si ocurre, limpiar el historial (`history -c && history -w`) y rotar la credencial.
- Cada despliegue deja una entrada al inicio de `HANDOFF.md` con el hash que corre en `p340` y los pasos que se ejecutaron.
