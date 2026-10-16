---
name: orquestar
description: Reparte una ronda de trabajo de AeroControl entre subagentes - Opus orquesta, Sonnet construye, Haiku verifica y busca - para no gastar tokens de más. Usar cuando una petición tenga varias partes independientes o mucho trabajo mecánico.
---

# Orquestar una ronda

## Quién hace qué

| Modelo | Rol | Ejemplos |
|---|---|---|
| **Opus** (esfuerzo medio) | Diseña, decide y establece cómo se hace; reparte, revisa, integra y publica el PR | Planificar, propuestas de diseño, resolver dudas con la persona, revisar lo entregado |
| **Sonnet** (esfuerzo medio) | Implementa lo que Opus dejó decidido | Código y pruebas, documentos, un PR por worktree |
| **Haiku** (esfuerzo medio) | Lo que Opus estime conveniente para no gastar de más | Revisión mecánica del diff, inventarios (`pendientes-github`), buscar dónde está algo, resumir salidas de pruebas o logs |

Al lanzar un subagente pasa siempre `model` explícito (`"opus"`, `"sonnet"` o `"haiku"`) y, para diseño, `subagent_type: "Plan"` (solo lee y propone). Orden de la persona (2026-10-16): **Opus diseña y decide, Sonnet implementa, Haiku revisa**; el cierre de PR, ramas y worktrees sigue `pendientes-github`.

## Orden

1. **Entender (Opus).** Separar el pedido en partes independientes; lo que dependa de una decisión de la persona se pregunta antes.
2. **Explorar (Haiku, opcional).** Ubicar archivos y dueños antes de repartir.
3. **Repartir (Sonnet, en paralelo).** Un agente por parte, con **dueños de archivos sin cruce**: el prompt dice qué edita y
   qué no toca. Si trabajan en el mismo repo, cada uno en su propio `git worktree`. Sin `git push` ni PR en los subagentes.
4. **Integrar (Opus).** Leer el informe, mirar el diff y correr `/verificar`.
5. **Verificar (Haiku).** Enlaces, inventarios y revisión mecánica al final.
6. **Publicar (Opus).** Rama `codex/<tema>`, PR, CI en verde. **Opus fusiona** con el CI verde y sin conflictos
   (decisión del usuario, 2026-10-05, en `AGENTS.md`); la persona **sólo despliega** en `p340`. Nunca `push --force`.

## Ahorro de tokens

- No dupliques búsquedas entre agentes.
- Prompts autosuficientes y cortos: contexto, archivos dueños, criterios de aceptación, cómo verificar, qué reportar.
- Informes concisos (archivos, decisiones, pruebas); los detalles se leen del diff.
- Si un agente arrancó con el modelo equivocado y lleva poco, detenlo y relánzalo; descarta lo hecho a medias.

## Lecciones de la ronda del 2026-10-16 (rediseño de barra y panel)

Lo del agente cortado y del informe de subagentes está en `pendientes-github` (Trampas conocidas).

- Con la ventana del navegador oculta innerWidth da 0 y todo mide 0: `resize_window` antes de medir.
