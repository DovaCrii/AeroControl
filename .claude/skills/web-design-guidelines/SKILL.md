---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

> Copia fijada (ver `.claude/skills/VENDOR.md`). Cambio respecto del original: las reglas se leen de
> `rules/command.md`, una copia local fijada a un commit, en vez de descargarlas de `main` en cada revisión.
> Así nadie puede cambiar las instrucciones del agente sin pasar por un PR de este repositorio.

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the rules from `.claude/skills/web-design-guidelines/rules/command.md` (local, pinned). Do **not** fetch them from the web.
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in that file
4. Output findings in the terse `file:line` format

## Stack notes

Rules written for React (`onClick`, `<Link>`, `onKeyDown`) apply to their HTML/Django template equivalents
(`<button>`, `<a href>`, native keyboard behaviour). Skip rules that only make sense for a JS framework the project does not use,
and say which ones you skipped.

## Usage

When a user provides a file or pattern argument:
1. Read `rules/command.md`
2. Read the specified files
3. Apply all rules
4. Output findings using the format specified in the rules

If no files specified, ask the user which files to review.
