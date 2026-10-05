---
name: abrir-pr
description: Entrega un bloque de AeroControl de punta a punta - rama codex/..., gate, PR, espera del CI y fusión con el CI verde. El usuario sólo despliega en p340. Úsala siempre que haya algo listo para llevar a main; nunca se empuja a main directo.
disable-model-invocation: true
argument-hint: "[área o fila, p. ej. t1-3-flightrequest]"
---

# Abrir, verificar y fusionar un PR

**Decisión del usuario, 2026-10-05:** el agente crea, verifica y **fusiona** sus PR con el CI verde y
sin conflictos; el usuario **sólo despliega** en `p340`. Reglas de `AGENTS.md` que no se negocian:
nunca se empuja a `main`, una rama por bloque (`codex/<área>`), un PR por intención, nunca
`push --force`.

## 0. Dónde estoy (antes de tocar nada)

El 2026-10-05 se hicieron diez commits en una rama que nadie miró y **ninguno llegó a `main`**,
aunque se dio por hecho que sí: `git push -q origin main` empujaba un `main` local que no se había
movido, y el `-q` ocultó «Everything up-to-date». Por eso:

1. `git branch --show-current` — **la rama, no se supone**. Si no es la que corresponde, parar.
2. `git status --short` y `git fetch`; `git log --oneline HEAD..origin/main`. Si divergió, parar y
   preguntar: no se fuerza.
3. **Nunca `-q` en un `push`**, ni se recorta su salida con `Select -Last`. La salida del push es la
   prueba de que subió.

## 1. Rama y verificación

4. Desde `main` actualizado: `git checkout -b codex/<área>`. Si hay trabajo sin commit en otra rama,
   se rescata con `cherry-pick`, nunca con `reset` ni `--force`.
5. `/verificar` en verde (`pwsh scripts/verify.ps1`, que incluye el *staging preflight* del CI).
6. La fila y su commit van **juntos** (`/cerrar-tarea`): `MASTER_PLAN.md`, `CHANGELOG.md` y, si cambió
   algo operativo, `HANDOFF.md`. **No se abre un PR sólo para `HANDOFF.md`**: cada uno cuesta una
   ejecución de CI de ~20 min (el repositorio tiene 2 000 min/mes y ya llegó a 1 802).

## 2. Subir y abrir

7. `git push -u origin <rama>` y **leer** la salida: debe nombrar la rama nueva.
8. `gh pr create -R DovaCrii/AeroControl --base main --head <rama> --title … --body-file <archivo>`.
   El cuerpo va en un archivo del *scratchpad* (el filtro de comandos rechaza ciertos caracteres en
   línea). Español, con estas secciones:
   - **Qué cambia** (una frase por cambio).
   - **Cómo se midió:** el gate y cifras, con fecha; y lo que se rompió a propósito para probar el test.
   - **Filas del plan** tocadas y su estado.
   - **Riesgos y lo que queda sin comprobar**, y el **paso de despliegue** (qué hay que hacer en `p340`).
   - Si cambió `AGENTS.md` o `.github/workflows/`, decirlo arriba y por qué.

## 3. Esperar y fusionar

9. `gh pr checks <n> -R DovaCrii/AeroControl --watch` (en segundo plano: tarda ~20 min).
10. Fusionar **sólo** con todas las comprobaciones en verde y `mergeStateStatus` = `CLEAN`:
    `gh pr merge <n> -R DovaCrii/AeroControl --merge --delete-branch`.
11. Si el CI falla o hay conflicto, **no se fusiona**: se lee el log (`gh run view <id> --log-failed`),
    se arregla la causa con un commit nuevo (o `merge` de `main` en la rama) y se vuelve a esperar.
    Un PR apilado se fusiona **después** de su base. Si el usuario dijo «no la fusiones», manda.

## 4. Comprobar que llegó

12. `git checkout main && git pull --ff-only`, y `git ls-remote origin refs/heads/main` debe dar el
    mismo hash que `git log --oneline -1`. **Ese hash es el que el usuario verá en `p340`.**
13. Terminar con: qué se fusionó, el hash de `main`, y los pasos de `/desplegar-p340`. No se da nada
    por entregado sin haber hecho el paso 12.

## Notas

- Si hay varias ejecuciones en la misma rama, `ci.yml` cancela las anteriores; no empujar de a poco.
- Si `gh` pide autenticación, es del usuario: no se intenta resolver.
- Un cambio que sólo toca documentación igual corre el CI completo; agrupar lo documental con el PR
  del bloque al que pertenece.
