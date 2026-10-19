---
name: desplegar-p340
description: Dicta, paso a paso, el despliegue de lo que falta en la VM p340, lee la terminal del usuario para confirmar que llegó y deja registrado el hash. El usuario pega los comandos; el agente no tiene acceso SSH. Úsala cuando hay algo fusionado en main sin desplegar.
disable-model-invocation: true
argument-hint: "[hash que corre hoy la VM - opcional]"
---

# Desplegar a `p340`

El usuario **sólo emite a la VM**; el agente no tiene SSH y no lo intenta. Rutas y comandos de apoyo en
`docs/dev/remote-vm-operations.md` y `docs/dev/ubuntu-vm-deploy.md`. En el repo público sólo van `/opt/aerocontrol`,
`/etc/aerocontrol.env` y marcadores `<…>`: nunca contraseñas ni datos reales de la VM.

## 0. Cuándo se despliega: **por tandas, no por PR** (decisión del usuario, 2026-10-07)

El agente **fusiona bloque tras bloque** y sigue con el siguiente **sin pedir desplegar** entre ellos.
Lo fusionado sin desplegar y lo pendiente se anotan en la primera entrada de `HANDOFF.md` (viaja en
el siguiente PR). Se despliega **una vez**, cuando:

- se terminaron los bloques que se pueden hacer sin una decisión del usuario, **o**
- el usuario lo pide, **o**
- producción está rota o hay un hallazgo de seguridad (ahí se despliega **ya**, sin esperar).

El despliegue une **todo** lo que hay entre el hash de la VM y `origin/main`, y el seguimiento de
`HANDOFF.md` ya dice qué lleva migración y qué lleva estáticos: no se vuelve a descubrir al desplegar.
Al terminar, el agente **lee la salida** (panel de Terminal o pegada) y sólo da por desplegado lo que
vio terminar en el hash de `origin/main`.

## 1. Qué falta

**Atajo:** `pwsh -NoProfile -File .claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash de
la VM>` hace lo de abajo (diff, clasificación y bloques) y escribe **sólo los comandos necesarios**; la
tabla y las reglas que siguen explican **por qué** son esos. Está en la skill `/terminar-bloques`, que
encadena todo el recorrido (bloques → PR → fusión → esto).

1. `git fetch` y `git log --oneline -1 origin/main` — **el hash que debe quedar en la VM**.
2. Qué corre hoy la VM: el argumento, la primera entrada de `HANDOFF.md`, o se le pide al usuario
   `git log --oneline -1` desde la VM.
3. `git diff --name-only <hash-de-la-VM>..origin/main` — **todo** lo que hay en medio, no sólo el
   último commit (un salto de una tanda a otra sin su migración tiró producción el 2026-08-31).

| Si el diff toca… | El bloque lleva… |
|---|---|
| `apps/*/migrations/*.py` | `backup` + `verify_backup` **antes**, `migrate --no-input` y después `showmigrations <app> \| tail -6` |
| `static/**` | `collectstatic --no-input` (que copie **al menos 1**; si copia 0 y se esperaba, no llegó) |
| `pyproject.toml` o `uv.lock` | `uv sync --no-dev` (debe instalar algo) |
| `templates/**`, `apps/**/*.py`, `locale/**/*.mo` | sólo reiniciar (el `.mo` está versionado: no hay `compilemessages`) |
| `docs/scheduled-operations.md` (timers nuevos) | **del usuario**: se le da el bloque `mkjob` y se comprueba con `list-timers` |

## 2. Camino principal: **un solo comando**, `scripts/deploy.sh` (LV-327)

```bash
cd /opt/aerocontrol && bash scripts/deploy.sh --dry-run   # primer uso: siempre; sólo lee, imprime el plan
cd /opt/aerocontrol && bash scripts/deploy.sh
```

Hace los pasos de A-D de abajo con sus comprobaciones y **aborta** en la primera señal de despliegue
fantasma (HEAD desprendido, árbol sucio, `uv sync` sin instalar, `collectstatic` en 0, health ≠ 200; el chequeo de salud manda `X-Forwarded-Proto: https`, LV-335). Pide
la contraseña de `sudo` **una vez**, no imprime el entorno y **nunca ejecuta un rollback**: lo imprime.
El usuario pega al chat sólo el bloque `=== RESUMEN` (≤10 líneas, sin entorno ni host). Opciones:
`--status`, `--backup`, `--allow-noop-sync`. **No instala timers** (siguen siendo del usuario).

### Plan B manual: **cuatro bloques cortos**, mirando la salida de cada uno

Si el script no puede correr. Probado el 2026-10-07 (dos despliegues sin un solo tropiezo). Cada bloque en su propio `bash`, **sin
`$` ni salida pegada**, y **sólo `&&` dentro del bloque, nunca `;`**: el `;` de una carga de entorno
mal escrita corta la cadena y un `git pull` fallado no frena el reinicio. Se espera la salida de cada
bloque antes de dictar el siguiente.

**A. Estado** (sólo lectura) — `cd /opt/aerocontrol && git status --short --branch && git log --oneline -1`
→ la primera línea debe ser `## main...origin/main`, **no** `## HEAD (no branch)`, y el hash, el que
se esperaba. Si dice otro hash, se dicta el despliegue desde **ese** y no desde el último conocido.

**B. Entorno y respaldo** — `set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && echo
"$DJANGO_SETTINGS_MODULE" && uv run python manage.py backup && uv run python manage.py verify_backup`
→ debe salir `config.settings.prod`, `Backup created` y `…: restorable.`. **El respaldo va antes del
`pull`** (es el de la base con el código viejo, y es el que se restaura si algo sale mal). Si el diff
**no** toca migraciones, el bloque se acorta a la carga y el `echo`, sin respaldo. El `sudo` pide la
contraseña **del usuario**: nadie la escribe en el chat ni como comando.

**C. Código y migraciones** — `git pull && git log --oneline -1 && uv run python manage.py migrate
--no-input` (con `uv sync --no-dev` entre el `pull` y el `migrate` si el diff toca `pyproject.toml` o
`uv.lock`). Debe mostrar `<hash-viejo>..<hash-nuevo>`, los archivos, y `Applying … OK` por cada
migración nueva. **El `pull` es el paso que se omitió dos veces el 2026-10-05**: «Already up to date»
con algo pendiente es una alarma. Sin migraciones, el bloque es sólo `git pull && git log --oneline -1`.

**D. Estáticos y reinicio** — `uv run python manage.py collectstatic --no-input && sudo systemctl
restart aerocontrol && systemctl is-active aerocontrol && git log --oneline -1` (sin el `collectstatic`
si el diff no toca `static/**`). Debe terminar en `active` y en el hash de `origin/main`, y el
`collectstatic` debe copiar **al menos 1**. El hash final es la única prueba de que llegó.

Si una contraseña del `sudo` sale mal, el bloque **sigue** al segundo intento y el resultado vale: no
se repite por eso.

### Trampas que el script y los bloques no cubren solos

- **Tras un rollback** (`git checkout <commit>`) la VM queda en HEAD desprendido: `git pull` no despliega nada y `uv sync`, `collectstatic` y el reinicio corren igual sobre el código viejo, sin error. Volver con `git checkout main` el mismo día.
- **Archivo que se va a versionar y ya existe sin versionar en la VM**: apartarlo allá antes (`mv` a `~`, no `rm`; `diff` después). Si no, `git pull` se niega y el resto corre sobre código viejo con respuestas plausibles.
- **Cargar el entorno con `set -a`** (`source` solo define variables de shell y `manage.py` cae a `config.settings.dev`); verificar `DJANGO_SETTINGS_MODULE` y `DB_PATH` con `echo` antes de migrar.
- **Un 500 tras desplegar**: `uv run python manage.py showmigrations <app> | tail -6`; una migración sin `[X]` con código nuevo que la usa lo explica sin leer el traceback.
- **Nunca se despliega encendido**: el service worker (`SERVICE_WORKER_ENABLED=False`; `docs/dev/postmortem-2026-09-08-service-worker.md`) ni un trabajo programado sin registrar su timer y verlo en `list-timers`. Una función que notifica se comprueba en producción (`--dry-run`, `list-timers`), no sólo con tests.

## 3. Confirmar leyendo la terminal

Con el script: leer el `=== RESUMEN` (terminal o pegado) y dar por desplegado sólo si dice
`DEPLOY OK`, `HEAD == origin/main: sí` y el hash nuevo; `DEPLOY FALLÓ en paso N` es parar y
diagnosticar, no reintentar. Con el plan B, `mcp__terminal__read_terminal` (≈80-150 líneas). Comprobar: la primera línea del `status`; que el `pull`
traiga la diferencia esperada; que `uv sync`/`collectstatic`/`migrate` hayan hecho **algo** si el diff lo
pedía; y el hash final. Las tres señales de que **no** llegó: `[behind N]`, `uv sync` sin instalar y
`migrate` sin aplicar. Si algo falla, **parar y diagnosticar** (`showmigrations`, el log), no repetir.

Si en la terminal aparece una contraseña tecleada como comando, **no repetirla**: avisar y pedir
`history -c && history -w`, y que se rote si se usa en otro lugar.

## 4. Dejar constancia

El hash que corre la VM entra en la primera entrada de `HANDOFF.md`, **dentro del siguiente PR del
bloque** (no se abre uno sólo para eso). Después, las comprobaciones de producción que corresponden
(`--dry-run`, `list-timers`): el gate verifica código, no el cableado de producción.
