# Skills externas fijadas

Copias revisadas y fijadas a un commit. No se actualizan solas: para subir de versión se repite la revisión
(leer `SKILL.md`, scripts y referencias; buscar red, escritura de archivos e instrucciones ocultas) en un PR propio.
Origen de la selección: artículo de Snyk «Las 8 mejores Claude Skills para ingenieros de UI/UX», revisado el 2026-10-19.

| Skill | Origen | Commit | Licencia | Cambios locales |
|---|---|---|---|---|
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | `56ea9cf` (2026-10-15) | MIT | Rutas de `search.py` relativas a la raíz del repo; sin `scripts/tests/` |
| `web-design-guidelines` | vercel-labs/agent-skills + vercel-labs/web-interface-guidelines | `063bee9` / `434b7f9` | MIT | Reglas locales en `rules/command.md`; nota de equivalencias HTML |
| `bencium-controlled-ux-designer` | bencium/bencium-claude-code-design-skill | `5de46a3` (2026-10-04) | MIT | Ninguno |
| `diseno-ui` | propia | — | la del repo | Método del repo y `scripts/contrast.py` (biblioteca estándar) |

## Revisión de seguridad (2026-10-19)

- `ui-ux-pro-max/scripts/*.py`: solo biblioteca estándar; sin red, sin `subprocess`; lee CSV locales. Escribe archivos
  únicamente con `--persist`, que `diseno-ui` prohíbe en este repo. Se quitó `scripts/tests/`.
- `web-design-guidelines`: el original descargaba sus reglas desde la rama `main` en cada uso (instrucciones remotas
  sin revisar); aquí se leen de `rules/command.md`, copia fijada de `vercel-labs/web-interface-guidelines@434b7f9`.
- `frontend-design`, `bencium-controlled-ux-designer`: solo Markdown; sin scripts ni `allowed-tools`.
- Sin caracteres ocultos ni instrucciones de exfiltración en ningún `.md`.

## Descartadas del artículo

- Vercel React Best Practices, Composition Patterns, React Native: el repo no usa React.
- AccessLint: hoy son cinco skills (`accessibility-scan`, `-fix`, `-audit`, `-inspect`, `-diff`) que dependen de su
  servidor MCP (`npx @accesslint/mcp@latest`, sin versión fija) y de Chrome DevTools. Se reemplaza por
  `diseno-ui/scripts/contrast.py` para el contraste. Si se adopta más adelante, fijar la versión del MCP (0.11.1 al 2026-10-19).
