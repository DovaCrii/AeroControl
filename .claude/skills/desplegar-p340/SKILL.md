---
name: desplegar-p340
description: Dicta, paso a paso, el despliegue de lo que falta en la VM p340, lee la terminal del usuario para confirmar que llegó y deja registrado el hash. El usuario pega los comandos; el agente no tiene acceso SSH. Úsala cuando hay algo fusionado en main sin desplegar.
disable-model-invocation: true
argument-hint: "[hash que corre hoy la VM - opcional]"
---

# Desplegar a `p340`

El usuario **sólo emite a la VM**; el agente no tiene SSH y no lo intenta. Detalle de reglas en
`.claude/skills/aerocontrol/references/despliegue-p340.md`.

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

## 2. Dictarlo en **cuatro bloques cortos**, mirando la salida de cada uno

Probado el 2026-10-07 (dos despliegues sin un solo tropiezo). Cada bloque en su propio `bash`, **sin
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

## 3. Confirmar leyendo la terminal

`mcp__terminal__read_terminal` (≈80-150 líneas). Comprobar: la primera línea del `status`; que el `pull`
traiga la diferencia esperada; que `uv sync`/`collectstatic`/`migrate` hayan hecho **algo** si el diff lo
pedía; y el hash final. Las tres señales de que **no** llegó: `[behind N]`, `uv sync` sin instalar y
`migrate` sin aplicar. Si algo falla, **parar y diagnosticar** (`showmigrations`, el log), no repetir.

Si en la terminal aparece una contraseña tecleada como comando, **no repetirla**: avisar y pedir
`history -c && history -w`, y que se rote si se usa en otro lugar.

## 4. Dejar constancia

El hash que corre la VM entra en la primera entrada de `HANDOFF.md`, **dentro del siguiente PR del
bloque** (no se abre uno sólo para eso). Después, las comprobaciones de producción que corresponden
(`--dry-run`, `list-timers`): el gate verifica código, no el cableado de producción.
