---
name: orquestar
description: Reparte una ronda de trabajo de AeroControl entre subagentes - Opus orquesta, Sonnet construye, Haiku verifica y busca - para no gastar tokens de más. Usar cuando una petición tenga varias partes independientes o mucho trabajo mecánico.
---

# Orquestar una ronda

## Quién hace qué

| Modelo | Rol | Ejemplos |
|---|---|---|
| **Opus** (sesión principal) | Entiende el pedido, decide, reparte, revisa, integra y publica el PR | Planificar, resolver dudas con la persona, revisar lo entregado |
| **Sonnet** | Construye | Código y pruebas, documentos, revisión independiente de un bloque |
| **Haiku** | Mecánico y de lectura | Buscar dónde está algo, inventarios, revisar enlaces, resumir salidas de pruebas o logs |

Al lanzar un subagente pasa siempre `model` explícito (`"sonnet"` o `"haiku"`); sin él podría heredar el modelo caro.

## Orden

1. **Entender (Opus).** Separar el pedido en partes independientes; lo que dependa de una decisión de la persona se pregunta antes.
2. **Explorar (Haiku, opcional).** Ubicar archivos y dueños antes de repartir.
3. **Repartir (Sonnet, en paralelo).** Un agente por parte, con **dueños de archivos sin cruce**: el prompt dice qué edita y
   qué no toca. Si trabajan en el mismo repo, cada uno en su propio `git worktree`. Sin `git push` ni PR en los subagentes.
4. **Integrar (Opus).** Leer el informe, mirar el diff, correr `uv run pytest` y `uv run ruff check .`.
5. **Verificar (Haiku).** Enlaces, inventarios y revisión mecánica al final.
6. **Publicar (Opus).** Rama, PR, CI en verde. La persona revisa y fusiona.

## Ahorro de tokens

- No dupliques búsquedas entre agentes.
- Prompts autosuficientes y cortos: contexto, archivos dueños, criterios de aceptación, cómo verificar, qué reportar.
- Informes concisos (archivos, decisiones, pruebas); los detalles se leen del diff.
- Si un agente arrancó con el modelo equivocado y lleva poco, detenlo y relánzalo; descarta lo hecho a medias.
