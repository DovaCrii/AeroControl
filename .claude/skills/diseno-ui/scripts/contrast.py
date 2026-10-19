#!/usr/bin/env python3
"""Contraste WCAG 2.x de los tokens de color de un CSS (solo biblioteca estándar).

Lee las variables ``--x: #hex | rgb() | var(--y)`` de los bloques de tema (``:root``,
``:root[data-theme="dark"]``, ``[data-bs-theme="dark"]`` y los mismos dentro de
``@media (prefers-color-scheme: dark)``), arma un tema claro y uno oscuro, y mide pares
texto/fondo.

Uso, desde la raíz del repo:

    python .claude/skills/diseno-ui/scripts/contrast.py <css>... --pair ink:bg --pair ink-2:sheet
    python .claude/skills/diseno-ui/scripts/contrast.py <css>... --auto      # explora pares probables
    python .claude/skills/diseno-ui/scripts/contrast.py <css>... --list      # lista los tokens
    python .claude/skills/diseno-ui/scripts/contrast.py --hex "#1F2430:#FAF8F3"  # colores sueltos

Umbral por defecto 4.5 (texto normal AA). ``--min 3`` para texto grande, iconos y bordes de
controles. Sale con código 1 si algún par de ``--pair`` queda bajo el umbral o nombra un token inexistente.
Colores con transparencia o ``color-mix()`` no se miden: se informan como «no medible».
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DECL = re.compile(r"--([\w-]+)\s*:\s*([^;{}]+)")
THEME_PART = re.compile(r"^(?:html|:root)?(?:\[[^\]]+\])*(?::not\(\[[^)]*\]\))?$")
TEXT_HINT = re.compile(r"^(?!on-|px-).*(^|-)(text|ink|fg|muted|label)(-\d|-|$)", re.I)
SURF_HINT = re.compile(r"^(bg|surface|sheet|card|paper|panel)|-(bg|surface)$", re.I)


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def theme_blocks(css: str):
    """Devuelve (tema, cuerpo) por cada bloque de variables de tema, en orden de fuente."""
    out, stack, start = [], [], 0
    for i, ch in enumerate(css):
        if ch == "{":
            stack.append(css[start:i].strip())
            start = i + 1
        elif ch == "}":
            body = css[start:i]
            sel = stack.pop() if stack else ""
            ctx = " ".join(stack + [sel])
            parts = [p.strip() for p in sel.split(",")]
            if sel and all(THEME_PART.match(p) for p in parts) and "--" in body:
                dark = "dark" in ctx
                out.append(("oscuro" if dark else "claro", body))
            start = i + 1
    return out


def load(paths):
    themes = {"claro": {}, "oscuro": {}}
    for p in paths:
        css = strip_comments(Path(p).read_text(encoding="utf-8"))
        for theme, body in theme_blocks(css):
            for name, value in DECL.findall(body):
                themes[theme][name] = value.strip()
    merged = dict(themes["claro"])
    merged.update(themes["oscuro"])
    return {"claro": themes["claro"], "oscuro": merged if themes["oscuro"] else {}}


def resolve(tokens, value, depth=0):
    m = re.fullmatch(r"var\(\s*--([\w-]+)\s*(?:,\s*(.+))?\)", value.strip())
    if m and depth < 20:
        ref = tokens.get(m.group(1), m.group(2))
        return resolve(tokens, ref, depth + 1) if ref else None
    return value.strip()


def to_rgb(value):
    if value is None:
        return None
    v = value.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) == 8 and h[6:] != "ff":
            return None
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(([^)]+)\)", v)
    if m:
        nums = re.split(r"[\s,/]+", m.group(1).strip())
        alpha = nums[3] if len(nums) >= 4 else "1"
        full = 100 if alpha.endswith("%") else 1
        if float(alpha.rstrip("%")) < full:
            return None
        return tuple(int(float(n)) for n in nums[:3])
    return None


def luminance(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def measure(tokens, fg, bg):
    a = to_rgb(resolve(tokens, tokens.get(fg, "")))
    b = to_rgb(resolve(tokens, tokens.get(bg, "")))
    if fg not in tokens or bg not in tokens:
        return None, "token inexistente"
    if a is None or b is None:
        return None, "no medible"
    return ratio(a, b), ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("css", nargs="*")
    ap.add_argument("--hex", action="append", default=[], help="#texto:#fondo")
    ap.add_argument("--pair", action="append", default=[], help="texto:fondo, sin '--'")
    ap.add_argument("--min", type=float, default=4.5)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    fails = 0
    for pair in args.hex:
        fg, bg = (to_rgb(c) for c in pair.split(":", 1))
        if fg is None or bg is None:
            print(f"  ?  {pair}: no medible")
            fails += 1
            continue
        r = ratio(fg, bg)
        fails += r < args.min
        print(f"  {'OK' if r >= args.min else 'NO'} {r:5.2f}:1  {pair}")
    if not args.css:
        if not args.hex:
            ap.error("indica archivos CSS o --hex")
        return 1 if fails else 0
    themes = {k: v for k, v in load(args.css).items() if v}

    if args.list:
        for t, toks in themes.items():
            print(f"## {t} ({len(toks)} tokens)")
            for n, v in toks.items():
                print(f"  --{n}: {v}")
        return 0

    pairs = [tuple(p.split(":", 1)) for p in args.pair]
    if args.auto:
        base = themes.get("claro", {})
        texts = [n for n in base if TEXT_HINT.search(n)]
        surfaces = [n for n in base if SURF_HINT.search(n)]
        pairs += [(f, b) for f in texts for b in surfaces]
    if not pairs:
        ap.error("indica --pair texto:fondo, --auto o --list")

    for t, toks in themes.items():
        print(f"## Tema {t}")
        for fg, bg in pairs:
            r, why = measure(toks, fg, bg)
            if r is None:
                if not args.auto:
                    fails += why == "token inexistente"
                    print(f"  ?  --{fg} sobre --{bg}: {why}")
                continue
            ok = r >= args.min
            if not ok and not args.auto:
                fails += 1
            if args.auto and ok:
                continue
            print(f"  {'OK' if ok else 'NO'} {r:5.2f}:1  --{fg} sobre --{bg}")
    if args.auto:
        print("(--auto: solo pares bajo el umbral; confirmar el uso real)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
