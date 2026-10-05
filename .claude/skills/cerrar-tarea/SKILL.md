---
name: cerrar-tarea
description: Cierra una fila del plan de AeroControl (LV-N, T1.3, UX-nn) - comprueba el criterio, marca la fila, escribe CHANGELOG y HANDOFF y deja el commit listo. Una fila cerrada y su commit van juntos.
disable-model-invocation: true
argument-hint: "<código de fila, p. ej. LV-270 o T1.3>"
---

# Cerrar la fila `$ARGUMENTS`

La fila y su commit van **juntos**: una fila que falta es trabajo que el próximo en llegar puede
rehacer (`LV-186`), y una marcada sin cumplirse es el tablero mintiendo.

1. **Leer la fila sin abrir el plan entero:**
   `python .claude/skills/aerocontrol/scripts/plan_query.py --id $ARGUMENTS`. Si la fila no existe,
   se crea (`LV-N` siguiente al último de `plan_query.py --ghosts`/`--id LV-27`).
2. **Antes de dar la premisa por buena, `grep` del código que la fila describe.** El tablero miente en
   las dos direcciones (un `⬜` ya hecho, un `✅` con premisa vencida).
3. **El criterio de la fila, comprobado:**
   - Un bug: una prueba que **falla sin el arreglo** — rompe el arreglo una vez, corre, restaura.
   - Una pantalla: se **mira** en el demo (`scripts/run-demo.ps1`), no sólo se mide.
   - Una cifra o un color: se **calcula**, no se lee del navegador.
   - Lo que no se pudo comprobar **no se marca ✅**: va 🔶 con qué falta y quién lo cierra.
4. `/verificar` en verde. «En verde» sólo si se vio la salida en esta sesión.
5. **`MASTER_PLAN.md`:** la fila en el bloque que corresponde (las `LV` nuevas, arriba, de la más nueva
   a la más antigua), con cifras medidas **y fecha**, lo que **no** se cambió a propósito, y el **paso
   de despliegue**. Un retiro «de pantalla y no de base» lleva escrita su condición de cierre.
6. **`CHANGELOG.md`:** una entrada en `[Unreleased]`, en lenguaje de quien usa la aplicación.
7. **`HANDOFF.md`**, sólo si cambió algo operativo (qué falta desplegar, qué decide el usuario). Debe
   seguir siendo corto: lo viejo va a `docs/dev/handoff-archive.md`.
8. Traducciones nuevas **a mano** en el `.po`, español neutro sin voseo, y `.mo` recompilado con
   `scripts/compile_translations.py`.
9. Un commit por intención, mensaje en español, imperativo y con ámbito (`fix(ui): …`), por archivo
   con `git commit -F`. La entrega la hace `/abrir-pr`.
10. Terminar diciendo: qué se cerró, con qué medida y qué queda abierto.
