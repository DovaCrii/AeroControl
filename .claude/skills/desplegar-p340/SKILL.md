---
name: desplegar-p340
description: Dicta, paso a paso, el despliegue de lo que falta en la VM p340, lee la terminal del usuario para confirmar que llegó y deja registrado el hash. El usuario pega los comandos; el agente no tiene acceso SSH. Úsala cuando hay algo fusionado en main sin desplegar.
disable-model-invocation: true
argument-hint: "[hash que corre hoy la VM - opcional]"
---

# Desplegar a `p340`

El usuario **sólo emite a la VM**; el agente no tiene SSH y no lo intenta. Detalle de reglas en
`.claude/skills/aerocontrol/references/despliegue-p340.md`.

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

## 2. Dictarlo, **uno por bloque**, mirando la salida de cada uno

Nunca encadenado: el `;` de la carga del entorno corta la cadena `&&` y un `git pull` fallado no frena
el reinicio. Cada comando en su propio bloque `bash`, **sin `$` ni salida pegada**:

1. `cd /opt/aerocontrol && git status --short --branch` → la primera línea debe ser
   `## main...origin/main`, **no** `## HEAD (no branch)`.
2. `git pull` → debe mostrar `<hash-viejo>..<hash-nuevo>` y los archivos. **Es el paso que se omitió
   dos veces el 2026-10-05** (`collectstatic` copió 0 archivos y el `git log` no cambió): se pide
   expresamente, y «Already up to date» con algo pendiente es una alarma.
3. `set -a && source <(sudo cat /etc/aerocontrol.env) && set +a` — **antes** de cualquier `manage.py`.
   El `sudo` pide la contraseña **del usuario**: nadie la escribe en el chat ni como comando.
4. Los pasos de la tabla de arriba, en ese orden (`uv sync`, `backup`, `migrate`, `collectstatic`).
5. `sudo systemctl restart aerocontrol && git log --oneline -1` → el hash **debe coincidir** con el de
   `origin/main`. Es la única prueba de que llegó.

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
