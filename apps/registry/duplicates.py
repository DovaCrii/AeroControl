"""LV-142: quién tiene ya este valor, para poder nombrarlo en el error.

Cada función devuelve **la fila** que ocupa el valor, no un booleano: el mensaje
de un duplicado sin el nombre del registro que lo tiene manda a buscarlo a mano
por toda la app, que es justo el trabajo que el aviso viene a ahorrar.

Tres reglas que valen para todas y que no son opcionales:

- **No se filtra `is_active`.** El índice único de la base no sabe de archivado,
  y `merge_operators` archiva el duplicado en vez de borrarlo
  (`apps/registry/merge.py`), así que en producción hay filas archivadas con su
  `employee_id` todavía ocupado. Filtrar por activas diría "no hay duplicado" y
  el `INSERT` reventaría igual — el mismo 500 que esto viene a eliminar. Es
  además lo que hace Django: `UniqueConstraint.validate()` consulta
  `_default_manager`, y `BaseModel` no define uno propio.
- **`exclude_pk`**, para que editar una fila no choque consigo misma.
- **`tenant_id` obligatorio y por keyword** donde la constraint lo incluye. La
  matrícula y el número de serie de una aeronave son `unique=True` globales, así
  que ésas no lo llevan: acotarlas por tenant sería más laxo que la base.

La coincidencia va con `__iexact` sobre el valor **ya normalizado** por quien
llama. Eso es más estricto que el índice de la base, que es el lado seguro:
puede avisar de un duplicado que la base habría aceptado, nunca lo contrario.
"""

from .models import Aircraft, CostCenter, Operator


def _first(queryset, exclude_pk):
    """La fila más antigua que ocupa el valor, o None.

    Ordenada por `created_at` a propósito: sin orden explícito, cuál de dos
    duplicados nombra el mensaje dependería del plan de consulta, y un aviso que
    señala a un registro distinto en cada intento no se puede seguir.
    """
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.order_by("created_at").first()


def operator_with_employee_id(employee_id, *, tenant_id, exclude_pk=None):
    """El operador que ya tiene ese número de empleado en este tenant."""
    if not employee_id:
        return None
    return _first(
        Operator.objects.filter(tenant_id=tenant_id, employee_id__iexact=employee_id),
        exclude_pk,
    )


def operator_with_rut(rut, *, tenant_id, exclude_pk=None):
    """El operador que ya tiene ese RUT en este tenant (LV-143).

    Comparación exacta: el RUT llega en su forma canónica (`normalize_rut`), que
    ya resolvió puntos, guión y la K minúscula.
    """
    if not rut:
        return None
    return _first(
        Operator.objects.filter(tenant_id=tenant_id, rut=rut),
        exclude_pk,
    )


def cost_center_with_code(code, *, tenant_id, exclude_pk=None):
    """El centro de costo que ya tiene ese código en este tenant."""
    if not code:
        return None
    return _first(
        CostCenter.objects.filter(tenant_id=tenant_id, code__iexact=code),
        exclude_pk,
    )


def aircraft_with_serial(serial_number, *, exclude_pk=None):
    """La aeronave que ya tiene ese número de serie.

    Sin tenant: `Aircraft.serial_number` es `unique=True` global, porque el
    serial lo pone el fabricante y no la organización.
    """
    if not serial_number:
        return None
    return _first(Aircraft.objects.filter(serial_number=serial_number), exclude_pk)


def aircraft_with_registration(registration, *, exclude_pk=None):
    """La aeronave que ya tiene esa matrícula. Sin tenant: es `unique=True` global."""
    if not registration:
        return None
    return _first(
        Aircraft.objects.filter(registration__iexact=registration), exclude_pk
    )
