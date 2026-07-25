# Qué cambia y por qué

<!-- Un párrafo. El problema antes que la solución: qué estaba mal o faltaba. -->

Cierra: <!-- MASTER_PLAN.md: T2.3 / R.10 / BLOQUE 1… o el hallazgo de AUDIT_CLAUDE.md -->

## Gate obligatorio

- [ ] `pwsh scripts/verify.ps1` pasa completo (no solo los tests)
- [ ] `uv run python manage.py makemigrations --check` sin cambios pendientes

## Definition of Done según el tipo de cambio

Marca solo las filas que apliquen; borra el resto. Las exigencias salen de
`AGENTS.md`, no son genéricas.

- [ ] **Modelo o campo nuevo** — migración con nombre descriptivo, constraints
  donde correspondan, y una prueba de cada constraint
- [ ] **Vista nueva** — prueba de 403 sin permiso, prueba de alcance de tenant si
  el modelo lo pide, strings traducidos
- [ ] **Comando de management** — prueba del camino feliz y de un camino de error
  real, no un `CommandError` trivial
- [ ] **Formulario** — una prueba por cada regla de `clean()` / `add_error()`
- [ ] **Corrección de bug** — una prueba que falla sin el arreglo y pasa con él
- [ ] **Plantilla** — `apps/core/test_templates.py` sigue verde
- [ ] **Cadenas de interfaz** — `.po` actualizado y `.mo` recompilado con
  `scripts/compile_translations.py` (nunca editado a mano)
- [ ] **Cambio visual** — revisado en el navegador en tema claro **y** oscuro,
  con captura si el cambio es de color, contraste o espaciado

## Riesgo

- [ ] Toca datos existentes (migración de datos, comando que escribe, borrado).
  Si sí: cómo se revierte →
- [ ] Cambia permisos o quién ve qué. Si sí: qué rol gana o pierde acceso →
- [ ] Nada de lo anterior

## Lo que queda fuera

<!-- Qué NO cubre este PR y por qué, para que no se dé por cerrado de más.
     Si el alcance se recortó, dilo aquí en lugar de dejarlo implícito. -->
