---
name: verificar
description: Corre el gate de AeroControl (scripts/verify.ps1) y devuelve un resumen corto. Úsala antes de dar algo por terminado, de cerrar una fila o de abrir un PR; nunca se dice «en verde» sin haber visto su salida en esta sesión.
---

# Verificar

El gate completo tarda **3-7 minutos** y vuelca miles de líneas (cobertura por archivo): no se corre
a pelo ni se pega entero al contexto.

1. `pwsh scripts/verify.ps1 2>&1 | Select-Object -Last 14` con `timeout` de 600 000 ms.
2. **En verde** cuando el final dice `verify.ps1: all checks passed`. Informar en una línea: cuántas
   pruebas pasaron y que `ruff`, `bandit`, `pip-audit` y el *staging preflight* pasaron.
3. **Si falla**, la última línea nombra el paso (`step failed (<nombre>)`). Lo que importa de pytest:
   `... | Select-String "FAILED|passed|failed"`. Abrir sólo el archivo de la prueba que falla.
   Arreglar la causa, no el síntoma, y volver a correr el gate **entero** (el paso siguiente puede
   depender del arreglado).
4. Para iterar sin el gate: `uv run pytest apps/<app>/<archivo>.py -q -p no:cacheprovider` y
   `uv run ruff check .` + `uv run ruff format --check .` (el CI corre **los dos** de ruff).

## Lo que el gate cubre y lo que no

- Cubre: `check` y `check --deploy`, migraciones al día, `pytest -n auto --cov` (umbral en
  `pyproject.toml`), `ruff`, `bandit`, `pip-audit` y el **mismo último paso que el CI**
  (`migrate` + `scale_readiness` + `backup` + `verify_backup`, sobre una base **temporal**).
- **No cubre** el navegador ni producción. Una pantalla se mira en el demo
  (`scripts/run-demo.ps1`); una función que notifica se comprueba en `p340` (`--dry-run`,
  `systemctl list-timers`). «Los tests pasan» no es «funciona».
- Los pasos de `verify.ps1` y de `.github/workflows/ci.yml` **deben coincidir**: el CI estuvo semanas en
  rojo (`LV-271`) porque el gate local no corría su último paso. Si se agrega un paso a uno, se agrega
  al otro.

## Trampas

- Un fallo que sólo aparece en paralelo: correr ese archivo solo y sin `-n`; si ahí pasa, la causa es
  estado compartido (disco fuera de `tmp_path`, caché de `ContentType`).
- Si un test falla y el diff no toca lo que afirma, **mirar la fecha antes que el diff**.
- El filtro de comandos de la herramienta rechaza algunas expresiones regulares en línea: ponerlas en
  un script del *scratchpad*.
