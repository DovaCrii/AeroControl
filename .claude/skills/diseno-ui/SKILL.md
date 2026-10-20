---
name: diseno-ui
description: Método de diseño visual y UX de AeroControl con las skills externas fijadas (ui-ux-pro-max, bencium-controlled-ux-designer, web-design-guidelines) y el verificador de contraste - qué skill usar en cada fase, qué fuentes de verdad mandan y qué se comprueba antes del PR. Usar al mejorar el aspecto de una pantalla, avanzar una fase de docs/ux-ui-plan.md, revisar UX/UI de una plantilla, o auditar accesibilidad y contraste.
---

# Diseño UI y UX

Política de modelos (`orquestar`): Opus decide y revisa, Sonnet implementa, Haiku corre la auditoría y el contraste.

## Fuentes de verdad (mandan sobre cualquier skill externa)

- `docs/ux-ui-plan.md`: veredicto, recorrido por pantalla, sistema de diseño objetivo (tokens en tres capas) y fases A–E.
- `static/css/app.css`: tokens `--ac-*` y `--sev-*`, claro y oscuro. `static/css/identity.css` **solo suma**: no redefine
  tokens ni colores de estado, y toda animación vive dentro de `prefers-reduced-motion: no-preference`.
- `docs/frontend-boundary.md`: Django + HTMX + Bootstrap 5; no se abre un segundo frontend.
- **No se crea** `design-system/MASTER.md` ni otro archivo de tokens: `ui-ux-pro-max` nunca se corre con `--persist`.
- Si una skill externa contradice el plan UX o los tokens medidos, no se aplica: se anota como pregunta abierta.

## Qué skill para qué

| Fase | Skill | Uso en AeroControl |
|---|---|---|
| Entender / Diseñar | `ui-ux-pro-max` | Solo consulta: `python .claude/skills/ui-ux-pro-max/scripts/search.py "<consulta>" --domain ux` (también `charts`, `typography`, `color`). Útil para tablas de trabajo, bandejas, formularios y dashboards. No hay stack Bootstrap en su lista: `--stack html-tailwind` es solo referencia de patrones, traducidos a Bootstrap + `--ac-*`. |
| Diseñar | `bencium-controlled-ux-designer` | Criterio de UX para una herramienta operativa: coherencia antes que novedad, densidad, revelación progresiva, recuperación de errores. Sus referencias `ACCESSIBILITY.md` y `MOTION-SPEC.md` complementan la sección 4 del plan. Pregunta antes de decidir, como pide el repo. |
| Verificar | `web-design-guidelines` | Sobre las plantillas tocadas: `/web-design-guidelines templates/<area>/*.html`. Las reglas de React se leen en su equivalente HTML/HTMX. |
| Verificar | `scripts/contrast.py` | Contraste WCAG de los tokens en claro y oscuro (ver abajo). |

## Contraste: pares base

```bash
python .claude/skills/diseno-ui/scripts/contrast.py static/css/app.css \
  --pair ac-text:ac-surface --pair ac-text-secondary:ac-surface \
  --pair ac-text-muted:ac-bg --pair ac-text-muted:ac-surface \
  --pair sev-critical-text:sev-critical-bg --pair sev-warning-text:sev-warning-bg \
  --pair sev-caution-text:sev-caution-bg --pair sev-advisory-text:sev-advisory-bg \
  --pair sev-nominal-text:sev-nominal-bg
```

Pares de «Cumplimiento» (`LV-359`, tokens `--id-cx-*` de `identity.css`; pasar los dos CSS):

```bash
python .claude/skills/diseno-ui/scripts/contrast.py static/css/app.css static/css/identity.css \
  --pair id-cx-ink:id-cx-heat-1 --pair id-cx-ink:id-cx-heat-2 \
  --pair id-cx-ink:id-cx-heat-3 --pair id-cx-ink:id-cx-heat-4 \
  --pair ac-text-muted:ac-surface
python .claude/skills/diseno-ui/scripts/contrast.py static/css/app.css static/css/identity.css --min 3 \
  --pair id-cx-edge:ac-surface --pair sev-critical-text:id-cx-track --pair sev-warning-text:id-cx-track \
  --pair sev-advisory-text:id-cx-track --pair sev-nominal-text:id-cx-track
```

Los rellenos de gráficos usan `--sev-*-text`, nunca `--sev-*-border`. Cuidado: un bloque `@media print` que reasigne
tokens en `html[data-theme="dark"]` hace que este script los lea como oscuros y mida mal; reasignarlos en `html body`.

Umbral 4.5:1; `--min 3` para iconos y bordes de controles. Al agregar un token de texto o de fondo, se suma su par en
el mismo PR. `--auto` explora; sus hallazgos se confirman con el uso real (p. ej. `--ac-text-muted` no se usa sobre los
fondos `--sev-*`, que llevan su propio `--sev-*-text`).

## Lecciones del repo que aplican a cambios visuales

- Los tests que verifican presentación comparan contra el objeto (`BUCKET_BADGE_CSS["overdue"]`), no contra un nombre de
  clase tecleado, y acotan la búsqueda a la región que afirman.
- Al retirar o renombrar una clase de presentación: `grep` de esa clase en `apps/*/test*.py` antes de darla por libre.

## Criterio de listo de un cambio visual

1. Ligado a una fase o ticket de `docs/ux-ui-plan.md` / `MASTER_PLAN.md`.
2. `contrast.py` con los pares base en verde y los nuevos agregados.
3. `web-design-guidelines` sin hallazgos nuevos en las plantillas tocadas.
4. Revisado a 375 px, claro y oscuro, y con movimiento reducido.
5. Gate completo: `pwsh scripts/verify.ps1`.
