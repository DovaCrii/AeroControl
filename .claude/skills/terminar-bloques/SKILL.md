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

6. Rama nueva **desde `origin/main` actualizado**, la prueba primero (y se ve fallar), implementar, y entonces
   `/cerrar-tarea` y `/abrir-pr` (rama, gate, PR, CI, fusión y comprobación; los scripts de arriba hacen
   `open_pr`/`wait_ci`/`merge_pr`). En `/cerrar-tarea` la línea del **«Seguimiento — fusionado sin
   desplegar»** de `HANDOFF.md` dice **qué lleva migración, qué lleva estáticos y cualquier advertencia**
   (se anota **al fusionar**, no al desplegar).
7. `git add` **por nombre** (no `-A`) y `git commit -F <archivo>`.
8. Lo propio de encadenar bloques:
    - **No se espera ocioso:** mientras corre el CI se empieza el bloque siguiente **en otra rama desde
      `origin/main`** (no desde la rama del PR en espera).
    - Conflicto casi seguro en `CHANGELOG.md` y `MASTER_PLAN.md` al fusionar el segundo PR en vuelo:
      `git fetch && git merge origin/main`, **conservar las dos entradas** (nunca descartar la de otro),
      línea en blanco entre entradas del `.po` y `.mo` regenerado con polib; correr las pruebas que tocan
      esos archivos y empujar. Si el merge cambia el hash, el CI corre de nuevo: es el costo de tener dos PR en vuelo.
## 3. Al terminar: lo que falta subir y los comandos justos

9. Pedir al usuario **un solo dato**: el hash que corre la VM (`git log --oneline -1` allá), o tomar el
    argumento / la primera entrada de `HANDOFF.md`. Si no se sabe, **se pregunta**: desplegar desde un
    hash equivocado repite el salto de tanda que tiró producción (2026-08-31).
10. `pwsh -NoProfile -File .claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash>`.
    Imprime los commits que faltan, qué llevan (migraciones, estáticos, dependencias) y los bloques
    **A** estado · **B** entorno (+ respaldo si hay migraciones) · **C** `pull` (+ `uv sync`/`migrate`) ·
    **D** (`collectstatic` si hay estáticos) + reinicio. **Sólo los que hacen falta**: sin migraciones no
    hay respaldo ni `migrate`; sin estáticos no hay `collectstatic`.
11. **Se dictan de a uno** (un bloque por mensaje, esperando la salida pegada o leída de la Terminal):
    el resto de las reglas de `/desplegar-p340` §2–§3 valen tal cual (el `sudo` pide la contraseña **del
    usuario**; nunca se repite una contraseña que aparezca en una salida; sólo cuenta como llegado el
    hash final de `origin/main`).
12. Con el despliegue confirmado: la primera entrada de `HANDOFF.md` pasa a «desplegados (`<hash>`)» y el
    seguimiento queda en «nada fusionado sin desplegar». Eso viaja en el **siguiente** PR, no en uno propio.

## 4. El informe final (siempre estas tres partes, cortas)

- **Fusionado:** una línea por PR con su número y fila; el hash de `main`.
- **Falta subir** (la salida de `deploy_plan.ps1`, resumida) **y los comandos**, empezando por el bloque A.
- **Queda sin hacer, y por qué:** cada fila saltada con su motivo (decisión del usuario, dependencia,
  tarea suya, refactor grande) y **qué decisión se necesita** para destrabarla. Lo que **no se pudo
  comprobar** (un gesto real del ratón, un portal ajeno, producción) se dice con esas palabras.

## No hacer

- Pedir desplegar entre bloques (salvo producción rota o hallazgo de seguridad), marcar ✅ lo que no se comprobó, o decidir por el usuario un tema de negocio.
- `push -q`, `--force`, `--no-verify`, empujar a `main`; dar por desplegado algo sin ver el hash final en la salida de la VM.
