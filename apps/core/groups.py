"""Canonical group names shared across apps.

Lives in `core` so the command that creates the groups (`bootstrap_roles`) and
the code that looks them up read the same literal instead of each carrying its
own copy of the name.
"""

# Recipients of the executive report. Not a permission role: it carries no
# permissions, it only decides who receives the mail.
REPORT_RECIPIENTS = "Dirección"
