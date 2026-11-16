# Banco de preguntas de las evaluaciones (REG-019): formato de carga

El banco de preguntas **no está en el repositorio** (es público y las preguntas con su
clave son el examen). Vive en la base (`registry.AssessmentQuestion`) y se carga con un
comando desde un archivo JSON **fuera del árbol versionado**: `private/` (ignorado por
git) o una ruta de la VM. Este documento describe sólo el **formato**; el ejemplo
`docs/examples/assessment_bank_example.json` es inventado (3 preguntas).

## Carga

```powershell
uv run python manage.py load_assessment_bank private/banco.json --dry-run   # valida, no escribe
uv run python manage.py load_assessment_bank private/banco.json             # carga
uv run python manage.py load_assessment_bank private/banco.json --replace   # además archiva lo que ya no viene
```

En la VM, en este orden: `deploy.sh` (migrate), luego `bash scripts/deploy.sh --manage load_assessment_bank <ruta> --dry-run` y, si no hay errores, el mismo sin `--dry-run`; con el archivo
copiado antes a una ruta fuera del repo (por ejemplo `private/`).

- **Idempotente** por `(tipo, modelo, número)`: volver a correrlo no duplica; una
  pregunta con el mismo número se actualiza.
- **Todo o nada**: si una pregunta es inválida no se escribe ninguna y el comando
  lista todos los problemas.
- `--replace` **archiva** (`is_active=False`, nunca borra) las preguntas de los tipos
  presentes en el archivo que éste ya no lista; **por par (tipo, modelo)**: un archivo con sólo las preguntas de un modelo no toca las comunes ni las de otros modelos. Nunca usar `--replace` en la primera carga.
- Se rechaza cualquier archivo dentro del repositorio salvo bajo `private/` (ignorado por git).

## Formato

Un objeto con `questions` (lista) y, opcional, `source` (procedencia, informativa).
Cada pregunta:

| Campo | Obligatorio | Descripción |
|---|---|---|
| `kind` | sí | `general`, `limitations` o `annual` (parte A del cuestionario anual) |
| `number` | sí | entero positivo; único por `(kind, family)` |
| `text` | sí | enunciado (los espacios se colapsan; no se cambia ninguna palabra) |
| `options` | sí | lista de al menos 2 `{"key": "a", "text": "..."}`; claves de una letra, distintas |
| `answer` | sí | la clave correcta (una de las `key`) |
| `source_ref` | no | dónde está en el Manual (informativo) |
| `family` | no | `code` de un `QualificationType`; sólo con `kind: "limitations"`: pregunta propia de ese modelo («las 3 del equipo»). Sin `family` es común a todos los modelos |

## Cómo se arma cada evaluación

| Evaluación | Preguntas | Umbral |
|---|---|---|
| Examen general | 20 de `general` | 75 % |
| Limitaciones y emergencias (por modelo) | 15 comunes + 3 del modelo | 100 % |
| Cuestionario anual | A: 10 de `annual` · B: limitaciones del modelo | A 75 % · B 100 % |

Si el banco tiene menos preguntas que el Manual pide, el intento se arma con las que
hay (se muestra cuántas) y los umbrales por parte se aplican igual. Sin ninguna
pregunta común del tipo la pantalla dice «El banco de preguntas no está cargado».
