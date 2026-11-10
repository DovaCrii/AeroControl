"""Quita los msgid duplicados del catalogo (se queda con la primera aparicion) y recompila el .mo.

Uso (dentro del worktree): python dedupe_po.py
Avisa si dos copias traen traducciones distintas (no las decide: se detiene).
"""

import sys

import polib

PO = "locale/es/LC_MESSAGES/django.po"
MO = "locale/es/LC_MESSAGES/django.mo"
po = polib.pofile(PO)
seen = {}
drop = []
for entry in po:
    key = (entry.msgctxt, entry.msgid, entry.msgid_plural)
    if key in seen:
        first = seen[key]
        if (first.msgstr, dict(first.msgstr_plural)) != (
            entry.msgstr,
            dict(entry.msgstr_plural),
        ):
            print(
                "DIFIEREN:",
                entry.msgid[:70],
                "|",
                first.msgstr[:50],
                "|",
                entry.msgstr[:50],
            )
            sys.exit(1)
        drop.append(entry)
    else:
        seen[key] = entry
for entry in drop:
    po.remove(entry)
po.save(PO)
po.save_as_mofile(MO)
print("duplicados quitados:", len(drop), "entradas:", len(po))
