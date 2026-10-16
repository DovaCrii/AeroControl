---
name: pendientes-github
description: Cierra lo que queda pendiente en GitHub de AeroControl - PR abiertos (propios y de dependabot), ramas ya fusionadas y worktrees sobrantes - con el reparto Opus decide, Sonnet implementa, Haiku revisa. Usar al terminar una tanda, antes de dictar un despliegue o cuando la persona pida «cerrar los pendientes de GitHub».
---

# Cerrar los pendientes de GitHub

Complementa a `terminar-bloques` (que hace los bloques de **código**) y a `orquestar` (quién hace qué). Esta skill
se ocupa de lo que se acumula **alrededor**: PR sueltos, ramas que ya están en `main` y copias de trabajo viejas.

## 1. Inventario (Haiku, solo lectura)

```powershell
pwsh .claude/skills/pendientes-github/scripts/inventario.ps1
```

Da PR abiertos con su estado y quién los abrió, ramas remotas ya fusionadas y worktrees (con cambios sin commitear
marcados). Un subagente Haiku puede correrlo y resumir; no decide nada.

## 2. Decidir (Opus, esfuerzo medio)

Por cada PR abierto, una de cuatro salidas. Se anota en el informe, no se hace en silencio:

| Caso | Qué hacer |
|---|---|
| Propio, `CLEAN`, CI verde | Fusionar con `terminar-bloques/scripts/merge_pr.ps1` |
| Propio, `DIRTY` por fusionar `main` | Fusionar `origin/main` en la rama (nunca rebase forzado ni `push --force`), resolver y volver a esperar el CI |
| Dependabot con el CI en rojo | Mirar **primero la causa** (`gh run view <id> --log-failed`); si es `uv.lock needs to be updated`, el bump no actualizó el lockfile: se rehace a mano en una rama `codex/deps-<tema>` con `uv lock --upgrade-package <paquete>` y se cierra el de dependabot citando ese PR |
| Antiguo (semanas) o que ya nadie recuerda | **Preguntar a la persona** antes de cerrar; nunca cerrar por inercia |

Un bump de **Django** o de **ruff** puede cambiar comportamiento o formato: va solo, con el gate completo, y un bump mayor
de ruff obliga a correr `ruff format` y revisar el diff. Nunca se mezclan dos dependencias en un PR.

## 3. Implementar (Sonnet, esfuerzo medio)

Un agente por PR de dependencia o de limpieza, **cada uno en su worktree**, con dueños de archivos sin cruce
(`pyproject.toml`/`uv.lock` solo lo toca uno a la vez: es el cuello de botella). El prompt exige: rama `codex/<tema>`,
gate `pwsh scripts/verify.ps1` completo, un commit, **sin push ni PR**, e informe de qué quedó sin hacer.

## 4. Revisar (Haiku, esfuerzo medio)

Revisión mecánica del diff: `localStorage` sin try/catch, animaciones fuera de `prefers-reduced-motion`, cadenas nuevas
sin traducción en el `.po` ni `.mo` recompilado, datos personales o rutas de VM, fila de `MASTER_PLAN.md` y entrada de
`CHANGELOG.md`. Informa archivo:línea o «sin hallazgos». No edita.

## 5. Publicar y fusionar (Opus)

`open_pr.ps1`, `wait_ci.ps1`, `merge_pr.ps1`, de `terminar-bloques`. Se lee la salida; la prueba de que algo llegó es
`git ls-remote origin refs/heads/main`.

## 6. Limpieza

- **Ramas remotas ya fusionadas:** `gh pr merge --delete-branch` ya las borra; las que queden se borran una a una con
  `git push origin --delete <rama>` **solo si el inventario las lista como fusionadas** y la persona lo confirma.
- **Worktrees:** `git worktree list`. Los de `.claude/worktrees/agent-*` de un agente que ya terminó se quitan con
  `git worktree remove <ruta>` **después de comprobar que su rama está en `origin/main`**; si tiene cambios sin commitear
  (el inventario los marca) **no se borra**: se retoma el agente con `SendMessage` para que los cierre.
- **Servidores de prueba** levantados para verificar en el navegador: detenerlos.

## Trampas conocidas

- Un agente que se cortó deja el trabajo **sin commitear** en su worktree: `git status --short` en su ruta antes de dar
  nada por perdido o por hecho; se retoma con `SendMessage`, que conserva su contexto.
- `mergeStateStatus` pasa a `UNKNOWN`/`DIRTY` cada vez que otro PR llega a `main`: es normal, se vuelve a consultar.
- Los conflictos típicos son `CHANGELOG.md` y el `.po`: conservar **ambos** lados y, en el `.po`, dejar línea en blanco
  entre entradas; el `.mo` se regenera con polib, nunca a mano.
- `gh pr checks` con «fail» a los 7–10 s casi siempre es un paso de preparación (lockfile, instalación), no una prueba.
