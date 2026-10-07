---
name: terminar-bloques
description: Termina todos los bloques pendientes de AeroControl sin parar - por cada uno rama, prueba primero, gate, fila, PR, CI, fusión y comprobación en GitHub - y al final lista lo que falta subir a p340 y da los comandos justos para emitirlos. El agente hace todo hasta GitHub; el usuario sólo emite en la VM. Úsala cuando el usuario pida «terminar los bloques», «avanzar en todo» o «dejar listo para subir».
disable-model-invocation: true
argument-hint: "[hash que corre la VM - opcional]"
---

# Terminar los bloques y dejar listo lo que se sube

**Decisión del usuario (2026-10-05 y 2026-10-07):** el agente crea, verifica y **fusiona** sus PR —todo
hasta GitHub— sin pedir permiso entre bloques; el usuario **sólo emite en la VM `p340`**, y se emite
**una sola vez al final** (`AGENTS.md`: «Quién fusiona» y «Despliegue por tandas»). Esta skill es el
recorrido completo. Las skills `/abrir-pr`, `/cerrar-tarea`, `/verificar` y `/desplegar-p340` siguen
mandando en el detalle de cada paso; acá se encadenan.

Los scripts viven en `.claude/skills/terminar-bloques/scripts/` (se llaman con `pwsh -NoProfile -File`):

| Script | Para qué |
|---|---|
| `open_pr.ps1 -Title … -BodyFile …` | sube la rama (salida **completa**), la comprueba en `origin` y abre el PR |
| `wait_ci.ps1 -Number N` | espera el CI hasta 9 min; salida 0 verde, 1 falló, 2 sigue (volver a llamarlo) |
| `merge_pr.ps1 -Number N` | fusiona **sólo** con todo en verde y `CLEAN`, y comprueba que el commit está en `origin/main` |
| `deploy_plan.ps1 -From <hash de la VM>` | lista lo que falta subir y escribe **sólo** los bloques de comandos necesarios |

## 1. Qué bloques se hacen

1. `git fetch`; `git log --oneline HEAD..origin/main`; `git branch --show-current`. Parar si algo está
   fuera de lugar (reglas de `/abrir-pr` §0).
2. Leer lo pendiente **sin abrir el plan entero:**
   `python .claude/skills/aerocontrol/scripts/plan_query.py --pending` (y `--id <fila>` de cada una).
3. **Antes de implementar una fila, `grep` del código que describe**: el tablero miente en las dos
   direcciones (un `⬜` puede estar hecho).
4. Se hace **todo lo que se puede hacer sin una decisión del usuario.** Se **salta**, y se anota por qué
   en el informe final, lo que:
   - depende de una decisión de negocio (umbrales, límites, metas: nunca se inventa un número);
   - exige una dependencia nueva (la política del repo no las admite sin que el usuario lo decida);
   - es una tarea del usuario en la VM (datos, timers, SMTP) o depende de otro producto (AeroLink);
   - es un refactor grande mientras el proyecto siga en pausa de estabilización (`AGENTS.md`).
5. Si una fila depende de otra, se hace **la de abajo primero** y se fusiona antes de empezar la
   siguiente: no se apilan PR.

## 2. Por cada bloque (un PR por intención)

6. Rama nueva **desde `origin/main` actualizado**: `git checkout -b codex/<área> origin/main`.
7. **La prueba primero**, y se ve fallar. Si un test sale verde de entrada sobre un defecto que acabas
   de arreglar, se rompe el arreglo una vez y se comprueba que el test cae (lección del 2026-09-01).
8. Implementar. Traducciones **a mano** en el `.po` (español neutro, sin voseo) y
   `uv run python scripts/compile_translations.py` para el `.mo`.
9. `/cerrar-tarea`: fila en `MASTER_PLAN.md`, entrada en `CHANGELOG.md` y, en `HANDOFF.md`, la línea del
   **«Seguimiento — fusionado sin desplegar»** con **qué lleva migración, qué lleva estáticos y
   cualquier advertencia** (se anota **al fusionar**, no al desplegar). Nunca un PR sólo por `HANDOFF.md`.
10. `pwsh scripts/verify.ps1` completo: sólo se dice «en verde» con la salida a la vista en esta sesión.
11. `git add` **por nombre** (no `-A` de todo), `git commit -F <archivo>` y el cuerpo del PR en un archivo
    del *scratchpad*: Qué cambia · Cómo se midió · Riesgos y lo que no se comprobó · Paso de despliegue.
12. `open_pr.ps1`, luego `wait_ci.ps1` (repetirlo si sale 2) y `merge_pr.ps1`.
    - **No se espera ocioso:** mientras corre el CI se empieza el bloque siguiente **en otra rama desde
      `origin/main`** (no desde la rama del PR en espera).
    - Conflicto casi seguro en `CHANGELOG.md` y `MASTER_PLAN.md` al fusionar el segundo PR en vuelo:
      `git fetch && git merge origin/main`, **conservar las dos entradas** (nunca descartar la de otro),
      correr las pruebas que tocan esos archivos y empujar. Si el merge cambia el hash, el CI corre de
      nuevo: es el costo de tener dos PR en vuelo.
    - Si el CI falla: leer el log, arreglar la causa con un commit nuevo y volver a esperar. Nunca
      `--force`, nunca `--no-verify`, nunca empujar a `main`.
13. **Comprobar que llegó:** `merge_pr.ps1` ya verifica que el commit está en `origin/main`; además
    `git ls-remote origin refs/heads/main` da el hash que verá la VM.

## 3. Al terminar: lo que falta subir y los comandos justos

14. Pedir al usuario **un solo dato**: el hash que corre la VM (`git log --oneline -1` allá), o tomar el
    argumento / la primera entrada de `HANDOFF.md`. Si no se sabe, **se pregunta**: desplegar desde un
    hash equivocado repite el salto de tanda que tiró producción (2026-08-31).
15. `pwsh -NoProfile -File .claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash>`.
    Imprime los commits que faltan, qué llevan (migraciones, estáticos, dependencias) y los bloques
    **A** estado · **B** entorno (+ respaldo si hay migraciones) · **C** `pull` (+ `uv sync`/`migrate`) ·
    **D** (`collectstatic` si hay estáticos) + reinicio. **Sólo los que hacen falta**: sin migraciones no
    hay respaldo ni `migrate`; sin estáticos no hay `collectstatic`.
16. **Se dictan de a uno** (un bloque por mensaje, esperando la salida pegada o leída de la Terminal):
    el resto de las reglas de `/desplegar-p340` §2–§3 valen tal cual (el `sudo` pide la contraseña **del
    usuario**; nunca se repite una contraseña que aparezca en una salida; sólo cuenta como llegado el
    hash final de `origin/main`).
17. Con el despliegue confirmado: la primera entrada de `HANDOFF.md` pasa a «desplegados (`<hash>`)» y el
    seguimiento queda en «nada fusionado sin desplegar». Eso viaja en el **siguiente** PR, no en uno propio.

## 4. El informe final (siempre estas tres partes, cortas)

- **Fusionado:** una línea por PR con su número y fila; el hash de `main`.
- **Falta subir** (la salida de `deploy_plan.ps1`, resumida) **y los comandos**, empezando por el bloque A.
- **Queda sin hacer, y por qué:** cada fila saltada con su motivo (decisión del usuario, dependencia,
  tarea suya, refactor grande) y **qué decisión se necesita** para destrabarla. Lo que **no se pudo
  comprobar** (un gesto real del ratón, un portal ajeno, producción) se dice con esas palabras.

## No hacer

- Pedir al usuario que despliegue entre bloques (salvo producción rota o hallazgo de seguridad).
- Marcar ✅ lo que no se comprobó; va 🔶 con lo que falta y quién lo cierra.
- `git push -q`, recortar la salida de un `push`, `--force`, `--no-verify`, empujar a `main`.
- Tomar una decisión de negocio por el usuario para poder cerrar una fila.
- Dar por desplegado algo sin ver el hash final en la salida de la VM.
