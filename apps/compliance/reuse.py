"""LV-200, paso 3: adjuntar un papel **que ya está cargado**, sin volver a subirlo.

Pedido del usuario, textual: *"cómo resolvemos cuando ya tengo otro documento de
la carta en otro permiso del mismo período, para no tener que subirlos siempre"*.

Los pasos 1 y 2 resolvieron el **almacenamiento**: al subir un archivo byte por
byte idéntico, la fila nueva apunta al que ya existe y no se escribe una segunda
copia. Lo que no resolvían es el **trabajo**: había que ir a buscar el archivo al
disco otra vez. Esto es lo que faltaba.

⚠️ **Se crea una fila nueva que comparte el archivo, no se comparte la fila.** Es
la misma decisión que tomó el paso 2, y por las mismas razones: de la relación
uno-a-uno entre documento y registro cuelgan el expediente
(`operational_dossier`), la atribución por faena (`LV-146`), el sujeto de cada
documento (`LV-186`) y **los porcentajes del informe de cumplimiento**, donde un
documento contado dos veces o ninguna mueve una cifra que va a la DGAC.
"""

from django.contrib.contenttypes.models import ContentType

from apps.compliance.reports import ALERT_COST_CENTER_PATHS


def cost_centre_of(entity):
    """La faena de `entity`, por el mismo camino que usan las alertas.

    Se lee de `ALERT_COST_CENTER_PATHS` en vez de declarar un segundo mapa: dos
    tablas que dicen dónde está la faena de cada modelo es cómo una de las dos
    se queda atrás el día que aparece un modelo nuevo — que es exactamente lo
    que `LV-204` tuvo que corregir en la tabla que ya existía.

    `None` cuando el modelo no está en el mapa o el registro no tiene faena, y
    quien llama trata ese `None` como *"acá no se ofrece reutilizar"*.
    """
    meta = entity._meta
    path = ALERT_COST_CENTER_PATHS.get(f"{meta.app_label}.{meta.model_name}")
    if not path:
        return None
    value = entity
    for step in path.split("__"):
        value = getattr(value, step, None)
        if value is None:
            return None
    return value


def reusable_documents(entity, doc_type_code):
    """Los documentos que son **el mismo papel para la misma faena** que `entity`.

    Cuatro condiciones, y ninguna es opcional:

    - **El mismo tipo de documento.** Una carta del mandante sólo puede
      reutilizarse como carta del mandante.
    - **La misma faena.** Una carta que el mandante de `CC691` emitió no autoriza
      a operar en `CC410`: adjuntarla allá no sería un atajo, sería un documento
      falso en el expediente.
    - **El mismo tipo de entidad.** Se ofrecen cartas de **otros permisos**, que
      es lo que el usuario pidió. Reutilizar entre tipos distintos —la carta de
      un plan geoespacial sobre un permiso— es especulación, y una lista con
      candidatos que nadie quiere es una lista que nadie mira.
    - **Vigente**, o sin vencimiento. Una carta ya vencida no puede cubrir un
      permiso nuevo, y ofrecerla invita a adjuntar papel muerto.

    Se excluye lo que ya cuelga de `entity`: reutilizar sobre sí mismo produciría
    dos filas del mismo papel en el mismo expediente, que es el defecto que
    `LV-230` acaba de sacar de esta misma pantalla.

    Y se exige `file_path` no vacío: una fila sin archivo no tiene nada que
    reutilizar. Existen —`LV-101` deja una al corregir— y ofrecerlas daría un
    documento adjunto que al abrirlo no muestra nada.
    """
    from django.utils import timezone

    from apps.compliance.models import Document

    centre = cost_centre_of(entity)
    if centre is None:
        return Document.objects.none()

    content_type = ContentType.objects.get_for_model(entity.__class__)
    model = entity.__class__
    meta = model._meta
    path = ALERT_COST_CENTER_PATHS[f"{meta.app_label}.{meta.model_name}"]
    # Los hermanos de `entity`: los registros del mismo tipo y la misma faena.
    siblings = (
        model._default_manager.filter(**{path: centre, "is_active": True})
        .exclude(pk=entity.pk)
        .values_list("pk", flat=True)
    )

    today = timezone.localdate()
    return (
        Document.objects.filter(
            content_type=content_type,
            object_id__in=list(siblings),
            doc_type__code=doc_type_code,
            is_current_version=True,
            is_active=True,
        )
        .exclude(file_path="")
        .exclude(expiry_date__lt=today)
        .select_related("doc_type")
        .order_by("-issue_date")
    )
