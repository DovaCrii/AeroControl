"""LV-392: every form control in `templates/` has an accessible name.

A `<select>` or `<input>` whose only hint is a placeholder (or nothing) is
announced by a screen reader as "edit text" / "combo box" with no purpose, and
that is exactly where filters live. The rule, applied to every template found
under `templates/` (nothing is listed by hand, so a new template is covered the
day it is created):

* `<label for="<id>">` pointing at the control, or
* `aria-label` / `aria-labelledby`, or
* the control is wrapped by a `<label>`.

Not controls that need a name of their own: `hidden`, `submit`, `button`,
`reset`, `image` inputs (the button text or `alt` names them), and anything in
`EXEMPT` below, each with its reason.

Template tags inside attributes make a real HTML parser unreliable, so this
works on the source with a tolerant regex: it only needs the opening tag.
"""

import pathlib
import re

from django.conf import settings

CONTROL_RE = re.compile(
    r"<(select|input|textarea)\b((?:\{[^}]*\}|\"[^\"]*\"|'[^']*'|[^>\"'{])*)>", re.S
)
LABEL_FOR_RE = re.compile(r"<label\b[^>]*\bfor=[\"']([^\"']+)[\"']", re.S)
LABEL_WRAP_RE = re.compile(
    r"<label\b[^>]*>(?:(?!</label>).)*?<(?:select|input|textarea)\b", re.S
)
ID_RE = re.compile(r"""\bid=["']([^"']+)["']""")
NAMED_RE = re.compile(r"\baria-label(?:ledby)?=")
SKIP_TYPES = {"hidden", "submit", "button", "reset", "image"}

# (template, snippet that identifies the control) -> why it needs no label of its own.
EXEMPT = {
    # Checkboxes and radios are named by the <label class="form-check-label"> that
    # sits beside them or wraps them; those are covered by the wrap/for rules, so
    # nothing is exempt on that account. Entries here are the real exceptions.
}


COMMENT_RE = re.compile(
    r"\{% comment %\}.*?\{% endcomment %\}|\{#.*?#\}|<!--.*?-->", re.S
)


def _strip_comments(source):
    """Blank out comments but keep their newlines, so reported lines stay true."""
    return COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), source)


def _templates():
    for templates_dir in settings.TEMPLATES[0]["DIRS"]:
        root = pathlib.Path(templates_dir)
        for path in sorted(root.rglob("*.html")):
            yield (
                str(path.relative_to(root)).replace("\\", "/"),
                path.read_text(encoding="utf-8"),
            )


def _unnamed(source):
    source = _strip_comments(source)
    label_targets = set(LABEL_FOR_RE.findall(source))
    wrapped_spans = [m.span() for m in LABEL_WRAP_RE.finditer(source)]
    found = []
    for match in CONTROL_RE.finditer(source):
        tag, attrs = match.group(1), match.group(2)
        type_match = re.search(r"""\btype=["']?([a-z]+)""", attrs)
        if tag == "input" and type_match and type_match.group(1) in SKIP_TYPES:
            continue
        if NAMED_RE.search(attrs):
            continue
        id_match = ID_RE.search(attrs)
        if id_match and id_match.group(1) in label_targets:
            continue
        # An id built by a template tag (`id="{{ x }}"`) is matched textually too.
        if any(start < match.start() < end for start, end in wrapped_spans):
            continue
        line = source.count("\n", 0, match.start()) + 1
        found.append((line, match.group(0)[:90].replace("\n", " ")))
    return found


def test_every_form_control_has_an_accessible_name():
    problems = []
    for name, source in _templates():
        for line, snippet in _unnamed(source):
            if any(name == t and key in snippet for (t, key) in EXEMPT):
                continue
            problems.append(f"{name}:{line}  {snippet}")
    assert not problems, (
        "Form controls without <label for>, aria-label or aria-labelledby:\n  "
        + "\n  ".join(problems)
    )


def test_the_guardian_detects_an_unlabelled_select():
    """Break-on-purpose check kept as a test: the scanner is not blind."""
    assert _unnamed('<select name="x" class="form-select"><option></option></select>')
    assert not _unnamed('<label for="a">A</label><select id="a" name="x"></select>')
    assert not _unnamed('<select aria-label="A" name="x"></select>')
    assert not _unnamed('<input type="hidden" name="x">')
