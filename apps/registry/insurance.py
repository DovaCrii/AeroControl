"""LV-159: la Resolución de la JAC pone la vigencia del seguro en la aeronave.

Reportado por el usuario con captura de producción, sobre `RPA-5534`: *"revisar,
subí la resolución JAC, sigue el error, revisar esta situación y corregir"*. La
ficha decía **"Póliza en ficha vigente hasta el 2026-08-08 · Vencida"** teniendo
adjunta, dos secciones más abajo, la *Resolución Exenta JAC (aprueba seguro RPA)*
del 2026-08-24 con vencimiento **2027-08-24**.

El círculo estaba cortado en el último tramo. `LV-117` creó el tipo de documento
para la resolución y lo llamó *"el papel que cierra el ciclo"*; `LV-81` modeló el
ciclo del estado (`missing → pending → filed → active`); y `LV-81b` corrigió la
mitad de presentación para que la escalera dejara de decir "vigente" sobre una
póliza caducada. Lo que **nadie** hacía era llevar la fecha del papel al campo:
`Aircraft.insurance_expiry` seguía con la vigencia de la póliza anterior, así que
la app insistía en "Vencida" después de cargar justamente el documento que la
renueva. Y el historial del trámite de la captura muestra el costo: seis
transiciones en once minutos, alguien intentando que la pantalla dijera la verdad
moviendo el estado, que no era donde estaba el problema.

**La resolución manda cuando va más lejos, y sólo entonces.** Una renovación
siempre mueve la vigencia hacia adelante: si el papel declara una fecha anterior a
la que está en ficha, no es una renovación —es un documento viejo que se está
archivando— y pisar la fecha buena con la vieja sería peor que no hacer nada.
"""

from django.contrib.contenttypes.models import ContentType

# LV-117 lo sembró con este código. Constante con nombre y no un literal en tres
# lugares: el día que cambie, hay uno que revisar.
JAC_APPROVAL_CODE = "jac-insurance-approval"


def jac_approval_expiry(aircraft):
    """La vigencia más lejana que declara una Resolución de la JAC en esta ficha.

    `is_current_version` y la más lejana: al reemplazar una resolución por su
    versión nueva, la que manda es la vigente; y con dos resoluciones vigentes
    —pasa cuando se amplía la cobertura— la que importa es la que llega más
    lejos, que es la que de verdad tiene autorizada la aeronave.
    """
    from apps.compliance.models import Document

    from .models import Aircraft

    return (
        Document.objects.filter(
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            doc_type__code=JAC_APPROVAL_CODE,
            is_active=True,
            is_current_version=True,
            expiry_date__isnull=False,
        )
        .order_by("-expiry_date")
        .values_list("expiry_date", flat=True)
        .first()
    )


def sync_insurance_expiry(aircraft, *, user=None):
    """Llevar la ficha a lo que dice la resolución. Devuelve la fecha nueva, o None.

    **La resolución es el verificador**, y eso es una decisión explícita del
    usuario (2026-08-26, textual): *"ahí lo que manda más que la póliza es la
    resolución de la JAC; que esté hoy autorizado, es el verificador"*. La póliza
    es el contrato con la aseguradora; la Resolución Exenta es el acto por el que
    la JAC **autoriza operar** con ella, y es lo que un fiscalizador pide.

    Por eso esto mueve **dos** cosas y no una:

    - `insurance_expiry`, a la vigencia que declara la resolución.
    - `insurance_status` a `active` **cuando la resolución está en vigor**, porque
      si el acto que autoriza está en ficha y vigente, la aeronave está
      autorizada. No es adelantarse al papel —que es lo que `LV-81b` y las
      compuertas del permiso existen para evitar—: es exactamente lo contrario,
      el estado siguiendo al papel que ya está.

    Lo que **no** hace es degradar: una resolución caducada no baja el estado.
    Para eso está la presentación de `LV-81b`, que sobre un estado `active` con
    fecha pasada dibuja "Póliza vencida" en vez de "vigente" — decir "vencida" es
    más honesto que borrar el hecho de que alguna vez estuvo autorizada.

    Devuelve `None` cuando no hay nada que mover: sin resolución en ficha, o
    porque la fecha que ya está va igual o más lejos. Una renovación siempre
    empuja la vigencia hacia adelante, así que un papel con fecha anterior a la
    que está en ficha no es una renovación sino un documento viejo que se
    archiva, y pisar la fecha buena con la vieja sería peor que no hacer nada.
    """
    from django.utils import timezone

    from .models import Aircraft

    declared = jac_approval_expiry(aircraft)
    if declared is None:
        return None
    moves_forward = (
        aircraft.insurance_expiry is None or aircraft.insurance_expiry < declared
    )
    in_force = declared >= timezone.localdate()
    should_activate = (
        in_force and aircraft.insurance_status != Aircraft.INSURANCE_STATUS_ACTIVE
    )
    if not moves_forward and not should_activate:
        return None

    fields = ["updated_at"]
    if moves_forward:
        aircraft.insurance_expiry = declared
        fields.append("insurance_expiry")
    if should_activate:
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_ACTIVE
        fields.append("insurance_status")
    # La bitácora de `LV-81` lee este atributo para atribuir el cambio; sin él la
    # fila nace muda, que es el defecto que `LV-101` encontró como "system". El
    # `pre_save` de `track_status_changes` escribe la fila del historial del
    # trámite, así que el salto a "Póliza vigente" queda registrado con quién y
    # cuándo, igual que si se hubiera apretado el botón.
    aircraft._changed_by_user = user
    aircraft.save(update_fields=fields)
    return declared if moves_forward else aircraft.insurance_expiry


def sync_insurance_from_document(document, user=None):
    """El gancho: una resolución guardada actualiza la aeronave de la que cuelga.

    Vive acá y se conecta por señal (`apps/registry/apps.py`) y no en cada vista
    de carga, porque hay **tres** caminos por los que un documento entra —alta,
    "Subir varios" y reemplazo de versión— y una regla escrita tres veces es una
    regla que uno de los tres deja de cumplir. `post_save` y no `pre_save`: el
    receptor escribe otra fila, y con `pre_save` esa escritura corre contra un
    guardado que todavía no aterrizó (la lección de `R6.1`, y está en AGENTS.md).
    """
    from .models import Aircraft

    if document.doc_type_id is None or document.expiry_date is None:
        return None
    if document.doc_type.code != JAC_APPROVAL_CODE:
        return None
    aircraft_type = ContentType.objects.get_for_model(Aircraft)
    if document.content_type_id != aircraft_type.id:
        return None
    aircraft = Aircraft.objects.filter(pk=document.object_id).first()
    if aircraft is None:
        return None
    return sync_insurance_expiry(aircraft, user=user)
