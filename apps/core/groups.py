"""Canonical group names shared across apps.

Lives in `core` so the command that creates the groups (`bootstrap_roles`) and
the code that looks them up read the same literal instead of each carrying its
own copy of the name.
"""

# Recipients of the executive report. Not a permission role: it carries no
# permissions, it only decides who receives the mail.
REPORT_RECIPIENTS = "Dirección"


def direction_emails():
    """Los correos del grupo Dirección, sin vacíos ni repetidos.

    LV-267: el respaldo de quien no tiene responsable asignado. Lo usan el resumen
    de vencimientos y el escalamiento de cartas del mandante; el vigilante de
    trabajos y los demás `check_*` tienen su propia consulta equivalente.
    """
    from django.contrib.auth import get_user_model

    # ⚠️ Se consulta **el usuario**, no el grupo. La forma anterior —partir de
    # `Group`, pedir `user__email` y excluir los vacíos sobre esa misma relación—
    # descarta **el grupo entero** si cualquiera de sus miembros tiene el correo
    # vacío (un `exclude` sobre una relación de muchos a muchos es «ningún
    # miembro cumple», no «quita a ese miembro»). Comprobado el 2026-10-05: con un
    # miembro con correo y otro sin él, devuelve `[]`. Una persona sin correo en
    # Dirección silenciaba a todos los demás.
    emails = (
        get_user_model()
        .objects.filter(groups__name=REPORT_RECIPIENTS, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    return sorted(set(emails))
