# CLAUDE.md · AeroControl

@AGENTS.md

## Cómo trabajamos (resumen; el estándar completo está en `docs/ESTANDAR_TRABAJO.md` de AeroAcademy)

`AGENTS.md` manda: si algo de abajo choca con él (prefijo de rama, quién fusiona, gate de calidad), vale lo de `AGENTS.md`.

- **Plan primero.** Antes de cambiar algo no trivial, propón un plan corto (qué, en qué archivos, cómo se prueba) y espera el visto bueno.
- **Bloques pequeños.** Una rama y un PR por cambio acotado: `codex/<tema>` (convención vigente del repo). Nunca trabajes directo sobre `main`.
- **Pruebas.** Escribe o ajusta pruebas junto con el código. Para iterar: `uv run pytest apps/<app>/tests.py` y `uv run ruff check .`.
  Antes de entregar, el gate completo: `pwsh scripts/verify.ps1` (incluye `uv run ruff format --check .`).
- **Flujo de PR.** Se sigue el de `AGENTS.md` y las skills `abrir-pr`, `cerrar-tarea`, `verificar` y `terminar-bloques`. Nunca `push --force`.
- **Privacidad (repositorio público).** Sin claves, `.env`, certificados, datos de clientes ni datos personales en git, logs ni pruebas.
  Lo privado va fuera del repo (variables de entorno, `DB_PATH`/`DOCUMENTS_DIR` externos) o en `private/` (ignorado por git).
  Revisión: `python tools/kit/privacy_scan.py` y la skill `revision-privacidad`.
- **Idioma.** Interfaz y documentación en español; código, nombres y URLs en inglés.
- **Alcance.** Haz solo lo pedido. Lo ambiguo se anota como pregunta abierta, no se decide solo.
- **No tocar** despliegue ni producción (`render.yaml`, `build.sh`, `docs/dev/ubuntu-vm-deploy.md`, `.claude/skills/desplegar-p340/`,
  `.claude/skills/terminar-bloques/scripts/deploy_plan.ps1`, `.env*`) sin que se pida explícitamente. Producción corre en la VM `p340`.
