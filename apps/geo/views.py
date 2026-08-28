from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.compliance.models import Document, DocumentType
from apps.operations.models import FlightPermission
from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup
from apps.core.audit import add_audit_sibling, set_audit_context
from apps.core.views import (
    CsvExportMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
)

from .forms import GeoPlanImportForm
from .kml import canonical
from .models import GeoPlan, GeoPlanVersion, WeatherReview

GEO_SOURCE_DOC_TYPE_CODE = "GEO_SOURCE"
# LV-180: el nombre que ve la gente. Era "Geo source" —inglés y jerga— en una
# app cuya interfaz es española y donde ese tipo de documento es, literalmente,
# el KMZ o KML que alguien subió.
#
# **El código NO se toca.** `GEO_SOURCE` lo referencian otras partes y no lo ve
# nadie; renombrarlo sería cambiar la llave por cambiar la etiqueta.
#
# **En español, y no es una excepción a la regla del proyecto.** Las cadenas
# fuente van en inglés porque el catálogo las traduce; esto es **dato**, no
# cadena fuente: viaja a la base y sale por `DocumentType.name`, que ningún
# `gettext` toca. Los demás tipos ya están en español porque nombran documentos
# reales —"Autorización de Operación RPA"—, así que "Geo source" era el único
# anglicismo del conjunto, y encima jerga: ese tipo de documento es, literal, el
# KMZ o KML que alguien subió.
#
# Va como constante y no como literal dentro del `get_or_create` porque la
# migración de datos renombra **exactamente** este texto, y dos copias de una
# cadena que deben coincidir son una que alguien va a actualizar sola.
GEO_SOURCE_DOC_TYPE_NAME = "Archivo KMZ/KML de origen"

# The status buttons offered on the plan detail, per current status. Each row is
# (from_status, url_name, label, css_class, permission). Un-approving requires
# the same permission as approving (see docs/dev/geo-editor-plan.md §5).
PLAN_TRANSITIONS = [
    (
        "draft",
        "geo-plan-start-editing",
        gettext_lazy("Start editing"),
        "btn-primary",
        "geo.change_geoplan",
    ),
    (
        "editing",
        "geo-plan-submit-review",
        gettext_lazy("Submit for review"),
        "btn-primary",
        "geo.change_geoplan",
    ),
    (
        "in_review",
        "geo-plan-approve",
        gettext_lazy("Approve"),
        "btn-success",
        "geo.approve_geoplan",
    ),
    (
        "in_review",
        "geo-plan-reject",
        gettext_lazy("Reject"),
        "btn-danger",
        "geo.approve_geoplan",
    ),
    (
        "rejected",
        "geo-plan-resume-editing",
        gettext_lazy("Resume editing"),
        "btn-primary",
        "geo.change_geoplan",
    ),
    (
        "approved",
        "geo-plan-reopen",
        gettext_lazy("Reopen for editing"),
        "btn-outline-secondary",
        "geo.approve_geoplan",
    ),
]


class GeoPlanListView(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    """LV-135: el listado gana buscador, filtro de estado y ver lo archivado.

    Pedido del usuario con la pantalla al frente: *"al momento de tener muchas
    planificaciones se podría dejar también un filtro […] y ahí se prende y apaga
    el filtro y se deja ver lo necesario, además si estaba archivada"*. Con siete
    planes de una sola faena ya cuesta encontrar uno, y esta pantalla era la única
    lista de la app **sin un solo filtro**: ni buscador, ni estado, ni nada.

    Y sin este filtro el archivado no serviría de nada: un plan archivado no
    tendría desde dónde restaurarse (`SearchMixin` ya trae el par `q` +
    `is_active`, así que no se inventa nada acá).
    """

    model = GeoPlan
    template_name = "geo/plan_list.html"
    htmx_template_name = "geo/_plan_rows.html"
    context_object_name = "plans"
    paginate_by = 25
    # LV-149: `source_document__title` es el nombre del archivo subido, y desde
    # que la columna 2 muestra **ese** nombre, buscar por lo que se ve en
    # pantalla tenía que dejar de fallar. `title` se conserva: los planes con
    # título escrito a mano siguen siendo buscables por él.
    search_fields = [
        "title",
        "source_document__title",
        "cost_center__code",
        "cost_center__name",
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        # **El defecto sigue siendo lo vigente.** `SearchMixin` sin parámetro no
        # filtra nada, y eso acá mostraría lo archivado mezclado con lo activo --
        # justo lo que archivar viene a evitar. Se ve archivado sólo al pedirlo.
        if self.request.GET.get("is_active") not in {"active", "archived"}:
            queryset = queryset.filter(is_active=True)
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)
        # LV-149: `source_document` entra al join porque la columna del archivo
        # lo lee en cada fila -- sin esto son 25 consultas extra por página.
        return queryset.select_related(
            "cost_center", "current_version", "source_document"
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = GeoPlan.STATUS_CHOICES
        context["current_status"] = self.request.GET.get("status", "")
        context["current_is_active"] = self.request.GET.get("is_active", "")
        return context


def _heading_extent(rows):
    """El tamaño del área, para el encabezado del plan. LV-183.

    Pedido del usuario mirando la hoja de campo: el radio estaba **al final**,
    bajo "Circunferencia y aeródromo", porque la hoja sigue el orden del
    formulario de SIGO — que es correcto para transcribir y malo para responder
    "¿de qué tamaño es esto?" al abrir el plan. Acá arriba no había nada del
    tamaño.

    **No se repite el número en la hoja**, que era la otra opción: son dos radios
    distintos en juego —el envolvente y el dibujado— y en una pantalla cuyo
    propósito es copiar sin equivocarse, el mismo dato dos veces a dos
    centímetros es una oportunidad de copiar el que no era.

    Con varias circunferencias devuelve **cuántas** en vez de un radio: ahí la
    pregunta del encabezado deja de ser el tamaño y pasa a ser cuántas hay que
    separar, y elegir el radio de una de ellas sería afirmar que las demás no
    existen.
    """
    if not rows:
        return None
    if len(rows) > 1:
        return {"count": len(rows)}
    row = rows[0]
    if row.get("radius_m") is None:
        return None
    # `is_enclosing` viaja para que la plantilla pueda decir que ese radio es el
    # del círculo que **cubre** el área y no el del área: afirmarlo a secas sería
    # el error que `LV-132` nombró.
    return {"radius_m": row["radius_m"], "is_enclosing": row["is_enclosing"]}


class GeoPlanArchive(ModelPermissionRequiredMixin, View):
    """LV-135: retirar un plan de la lista, sin borrarlo.

    Hasta acá **no había forma** de sacar un plan desde la app: los siete
    borradores de una carga de prueba se quedaban a la vista para siempre, y la
    única salida era el admin de Django — que no deja rastro en la auditoría de la
    app y no es un procedimiento que se le pueda pedir a nadie.

    **Archiva, no borra** (`is_active=False`), que es el "borrar" de este
    proyecto: la fila no se va, sale de los listados y vuelve con el filtro
    "Archivados". En una app de cumplimiento, lo que no se puede deshacer no se
    ofrece con un botón.

    **Y no archiva de golpe si el plan dejó rastro.** Muestra primero qué cuelga
    de él —solicitudes SIGO nacidas del plan, si alguna ya se presentó, el permiso
    vinculado, versiones y revisiones meteorológicas— el mismo molde que
    `CostCenterArchive` usa desde `V.31`. Decisión del usuario, textual: *avisar y
    dejar decidir*; las solicitudes **no se archivan en cascada**, porque son el
    registro de lo que se le pidió al Estado y esconderlas de un golpe sería
    esconder eso.
    """

    model = GeoPlan
    permission_action = "delete"

    def _dependents(self, plan):
        from apps.operations.models import FlightRequest

        requests = FlightRequest.objects.filter(source_plan=plan, is_active=True)
        return {
            "requests": requests.count(),
            # Presentada en SIGO es cualquier cosa menos "preparada": una vez
            # ingresada, allá existe un expediente que este plan explica.
            "filed_requests": requests.exclude(
                status=FlightRequest.STATUS_PREPARED
            ).count(),
            "permission": plan.flight_permission,
            "versions": plan.versions.count(),
            "weather_reviews": plan.weather_reviews.count(),
        }

    def _linked_permissions(self, plan):
        """Los permisos vivos que cuelgan del plan, por los **dos** caminos.

        LV-176: uno es `plan.flight_permission`; el otro son los permisos de las
        solicitudes SIGO que nacieron de este plan (`FlightRequest.source_plan`
        → `flight_permission`). Mirar sólo el primero dejaría fuera justo el
        caso de un plan multi-círculo, que es donde hay varios papeles y donde
        cerrarlos de a uno cuesta.
        """
        from apps.operations.models import FlightRequest

        pks = {plan.flight_permission_id} | set(
            FlightRequest.objects.filter(source_plan=plan).values_list(
                "flight_permission_id", flat=True
            )
        )
        pks.discard(None)
        return FlightPermission.objects.filter(pk__in=pks, is_active=True).order_by(
            "internal_folio"
        )

    def post(self, request, pk):
        plan = get_object_or_404(GeoPlan, pk=pk, is_active=True)
        dependents = self._dependents(plan)
        # LV-176, pedido del usuario: poder cerrar el plan **junto con** sus
        # permisos. Acompañado y no en cascada, decisión tomada con él: cada
        # permiso se archiva porque alguien marcó su casilla, no por arrastre.
        # Un permiso es un papel de la DGAC, y un cambio de estado que nadie
        # eligió es el que después nadie puede explicar.
        may_archive_permits = request.user.has_perm(
            "operations.delete_flightpermission"
        )
        linked = self._linked_permissions(plan)
        reason = request.POST.get("close_reason", "")
        detail = request.POST.get("close_reason_detail", "").strip()
        if any(bool(value) for value in dependents.values()):
            # LV-178: el motivo se pide **en esta pantalla**, la que ya existía,
            # y no se fuerza una confirmación nueva para los planes sin nada
            # colgando: `LV-135` decidió que ésos se archivan de una, con la
            # razón escrita —"una confirmación vacía sólo enseña a apretar sí sin
            # leer"— y sigue valiendo. En la práctica casi todo plan tiene al
            # menos una versión, así que casi todos pasan por acá.
            error = self._reason_error(reason, detail)
            if request.POST.get("confirm") != "1" or error:
                return render(
                    request,
                    "geo/plan_archive_confirm.html",
                    {
                        "object": plan,
                        "plan": plan,
                        "dependents": dependents,
                        "linked_permissions": linked,
                        "may_archive_permits": may_archive_permits,
                        "close_reason_choices": GeoPlan.CLOSE_REASON_CHOICES,
                        "close_reason": reason,
                        "close_reason_detail": detail,
                        "reason_error": error if request.POST.get("confirm") else None,
                    },
                )
            plan.close_reason = reason
            plan.close_reason_detail = detail if reason == GeoPlan.CLOSE_OTHER else ""
        archived = self._archive_chosen_permissions(
            request, linked, may_archive_permits
        )
        plan.is_active = False
        plan.save(
            update_fields=[
                "is_active",
                "close_reason",
                "close_reason_detail",
                "updated_at",
            ]
        )
        # LV-178: el motivo entra en la auditoría, y como el middleware comparte
        # el `metadata` entre la fila principal y sus hermanas, cada permiso
        # cerrado en este acto queda registrado con el mismo motivo. Es lo
        # correcto: se cerraron por eso.
        set_audit_context(
            request,
            plan,
            action="archived",
            metadata={"close_reason": plan.close_reason} if plan.close_reason else None,
        )
        messages.success(
            request,
            _("Plan archived. Use the Archived filter to find or restore it."),
        )
        if archived:
            messages.success(
                request,
                ngettext(
                    "%(count)s linked permit archived as well.",
                    "%(count)s linked permits archived as well.",
                    archived,
                )
                % {"count": archived},
            )
        return redirect("geo-plan-list")

    def _reason_error(self, reason, detail):
        """El aviso a mostrar, o `None`. LV-178.

        Se valida acá **además** de en `GeoPlan.clean()` porque el motivo llega
        de un POST suelto y no de un `ModelForm`: sin este paso, un motivo
        ausente pasaría al `save()` sin que nadie lo mire, y `clean()` sólo lo
        atraparía si alguien lo llamara.
        """
        valid = {code for code, _label in GeoPlan.CLOSE_REASON_CHOICES}
        if reason not in valid:
            return _("Choose why this plan is being closed.")
        if reason == GeoPlan.CLOSE_OTHER and not detail:
            return _("Say what the other reason was.")
        return None

    def _archive_chosen_permissions(self, request, linked, may_archive_permits):
        """Archiva los permisos marcados. Devuelve cuántos.

        **El permiso de archivar permisos se vuelve a comprobar acá**, y no sólo
        al dibujar las casillas: quien puede archivar planes no necesariamente
        puede archivar papeles de la DGAC, y esa distinción no puede depender de
        que el formulario que llega la haya respetado.

        Cada uno escribe **su propia** entrada de auditoría, no la del plan: si
        mañana alguien pregunta por qué se cerró ese permiso, la respuesta tiene
        que estar en el permiso.
        """
        if not may_archive_permits:
            return 0
        chosen = set(request.POST.getlist("archive_permission"))
        if not chosen:
            return 0
        count = 0
        for permission in linked:
            if str(permission.pk) not in chosen:
                continue
            permission.is_active = False
            permission.save(update_fields=["is_active", "updated_at"])
            add_audit_sibling(request, permission, action="archived")
            count += 1
        return count


class GeoPlanRestore(ModelPermissionRequiredMixin, View):
    """Traer de vuelta un plan archivado. Basta el permiso de cambio: reactivar
    no crea nada, y el molde es el de `RegistryRestore`."""

    model = GeoPlan
    permission_action = "change"

    def post(self, request, pk):
        plan = get_object_or_404(GeoPlan, pk=pk, is_active=False)
        plan.is_active = True
        plan.save(update_fields=["is_active", "updated_at"])
        set_audit_context(request, plan, action="restored")
        messages.success(request, _("Plan restored."))
        return redirect("geo-plan-detail", pk=plan.pk)


class GeoPlanDetailView(ModelViewPermissionRequiredMixin, DetailView):
    model = GeoPlan
    template_name = "geo/plan_detail.html"
    context_object_name = "plan"

    def get_queryset(self):
        return GeoPlan.objects.select_related(
            "cost_center", "flight_permission", "current_version", "source_document"
        )

    def get_context_data(self, **kwargs):
        from django.conf import settings
        from django.middleware.csrf import get_token
        from django.urls import reverse
        from django.utils.translation import gettext as _

        from apps.compliance.attachments import attached_documents_context

        context = super().get_context_data(**kwargs)
        plan = self.object
        # R10.5: los papeles que acompañan al KMZ -- el correo que pidió el
        # vuelo, el plano del cliente, la carta AIP con la que se confirmó el
        # AMC. Antes sólo se podían colgar del permiso, que en la etapa del plan
        # todavía no existe.
        context.update(attached_documents_context(self.request.user, plan))
        context["versions"] = plan.versions.order_by("-version_number")
        # LV-72: same traceability block as the flight permit. Oldest first
        # (SIGO numbers 1..N in the order things happened) with the actor's
        # groups prefetched -- unprefetched the role costs one query per row.
        context["history"] = (
            plan.history.select_related("changed_by_user")
            .prefetch_related("changed_by_user__groups")
            .order_by("sequence")
        )
        # OPS-7: when this plan's flight_permission link changed, and to what.
        # Shown unconditionally on this already geo.view_geoplan-gated page,
        # same as the Versions/Status history sections above.
        context["permission_links"] = plan.permission_links.select_related(
            "previous_permission", "new_permission", "changed_by_user"
        )
        current = plan.current_version
        # R10.1: lo que este KMZ dice para SIGO, **en la etapa del KMZ**. Antes
        # sólo se veía al separar el plan en solicitudes, lo que obligaba al
        # caso normal —un archivo con una circunferencia— a pasar por una acción
        # pensada para el excepcional. Se calcula al vuelo y no toca la base.
        #
        # Import local: `operations` importa de `geo` (los planes son suyos), y
        # subirlo al encabezado cerraría el círculo.
        from apps.operations.flight_requests import plan_sections

        context["sigo_rows"] = plan_sections(plan)
        # LV-150: la lista de solicitudes sale del menú, así que el
        # descubrimiento pasa a ser contextual -- desde el plan que las originó,
        # que es de donde se llega a ellas. Gateado por `view_flightrequest`: un
        # enlace que termina en 403 enseña a desconfiar de la pantalla (LV-130).
        # Import local por la misma razón que el de arriba: `operations` importa
        # de `geo`.
        from apps.operations.models import FlightRequest

        context["request_count"] = (
            FlightRequest.objects.filter(source_plan=plan, is_active=True).count()
            if self.request.user.has_perm("operations.view_flightrequest")
            else 0
        )
        # R10.8/LV-132: la nota que explica la fila, sólo cuando alguna muestra
        # el círculo envolvente en vez de lo dibujado.
        context["has_enclosing"] = any(
            row["is_enclosing"] for row in context["sigo_rows"]
        )
        context["heading_extent"] = _heading_extent(context["sigo_rows"])
        # Status buttons the user may use from the current status (GEO-9).
        context["status_actions"] = [
            {
                "url": reverse(url_name, args=[plan.pk]),
                "label": label,
                "css": css,
            }
            for from_status, url_name, label, css, perm in PLAN_TRANSITIONS
            if plan.status == from_status and self.request.user.has_perm(perm)
        ]
        # Editing (GEO-8) is offered only when the user may change the plan AND
        # the plan is in an editable state; the commit API re-checks both, this
        # only decides whether to render the editor UI. Read-only otherwise.
        editable = self.request.user.has_perm("geo.change_geoplan") and plan.is_editable
        context["editable"] = editable
        # Restoring a past version writes a new version, so it is a change too
        # (GEO-10): same gate as editing.
        context["can_restore"] = editable
        # Config for the map island. It fetches the canonical document from the
        # read API and (when editable) commits through the write API; business
        # rules live on the server.
        context["map_config"] = {
            "planId": str(plan.pk),
            "currentVersion": current.version_number if current else None,
            "baseVersion": current.version_number if current else 0,
            "contentUrl": (
                reverse(
                    "api-v1-geo-plan-version-content",
                    args=[plan.pk, current.version_number],
                )
                if current
                else None
            ),
            "commitUrl": reverse("api-v1-geo-plan-versions", args=[plan.pk]),
            # GEO-13: base URL for serving embedded KMZ icons; the island appends
            # ?name=<resource>. Only same-origin embedded resources are used.
            "resourceUrlBase": reverse("api-v1-geo-plan-resource", args=[plan.pk]),
            "csrfToken": get_token(self.request) if editable else "",
            "tileProviders": settings.GEO_TILE_PROVIDERS,
            "editable": editable,
            "iconBase": settings.STATIC_URL + "vendor/leaflet/images/",
            # GEO-12a: every version and where to fetch its canonical, so the
            # island can diff any two versions client-side (newest first).
            "versions": [
                {
                    "number": v.version_number,
                    "url": reverse(
                        "api-v1-geo-plan-version-content",
                        args=[plan.pk, v.version_number],
                    ),
                }
                for v in context["versions"]
            ],
            # The island is client-side JS (outside gettext's reach), so its
            # user-visible strings are localized here and passed through.
            "labels": {
                "untitled": _("Untitled"),
                "length": _("Length"),
                "area": _("Area"),
                "layers": _("Layers"),
                "features": _("Features"),
                "loading": _("Loading map…"),
                "error": _("The map could not be loaded."),
                "empty": _("This version has no geometry to show."),
                "name": _("Name"),
                "description": _("Description"),
                "apply": _("Apply"),
                "unsaved": _("Unsaved changes"),
                "saving": _("Saving…"),
                "conflict": _(
                    "The plan changed on the server. Reload to get the latest "
                    "version, then reapply your changes."
                ),
                "locked": _("This plan can no longer be edited."),
                "invalid": _("The change was rejected:"),
                "throttled": _("Too many saves in a row. Wait a moment."),
                "rescue": _("Download your local copy"),
                # GEO-11 layer tree
                "visible": _("Visible"),
                "duplicate": _("Duplicate"),
                "explode": _("Split into parts"),
                "rootDrop": _("Root — drop here or click to add new here"),
                # GEO-12a version diff
                "compare": _("Compare"),
                "diffExit": _("Exit comparison"),
                "diffAdded": _("Added"),
                "diffRemoved": _("Removed"),
                "diffChanged": _("Changed"),
                "diffVersion": _("Version"),
            },
        }
        context.update(self._weather_context(plan, current))
        return context

    @staticmethod
    def _weather_context(plan, current):
        """R8.1: forecast over this plan's area, for the day it is flown.

        Only asked for when the plan is tied to a permit with a start date --
        without a date there is no day to forecast, and a forecast for "today"
        on a plan flown next month would be worse than none. `weather` is None
        whenever the feature is off, the area has no bbox, or the provider did
        not answer; the template then shows nothing rather than an error.
        """
        from apps.core.weather import bbox_centroid, forecast_for

        centroid = bbox_centroid(current)
        permission = plan.flight_permission
        target_date = permission.valid_from if permission else None
        # The recorded reviews are listed whether or not a live forecast is
        # available right now: evidence already on record must not disappear
        # from the page because the provider is down today.
        reviews = plan.weather_reviews.select_related("reviewed_by")[:10]
        if centroid is None or target_date is None:
            return {
                "weather": None,
                "weather_date": None,
                "weather_reviews": reviews,
            }
        latitude, longitude = centroid
        return {
            "weather": forecast_for(latitude, longitude, target_date),
            "weather_date": target_date,
            "weather_reviews": reviews,
        }


class GeoPlanImportView(ModelPermissionRequiredMixin, FormView):
    model = GeoPlan
    permission_action = "add"
    template_name = "geo/plan_import.html"
    form_class = GeoPlanImportForm

    def get_initial(self):
        # LV-50: "Importar plan" from a flight permission's own detail page
        # prefills it, same pattern as maintenance-create?aircraft=.
        initial = super().get_initial()
        raw_permission = self.request.GET.get("flight_permission")
        if not raw_permission:
            return initial
        initial["flight_permission"] = raw_permission
        # LV-60: the cost center is not a second decision -- the permission
        # already has one, and the form now rejects a mismatch. Showing it
        # filled in makes that visible instead of asking again.
        # `.filter(pk=...)` on a UUIDField raises on a malformed value, so this
        # is guarded the same way as the compliance report's filters (LV-54):
        # a bad query string leaves the field empty, it does not 500.
        try:
            permission = (
                FlightPermission.objects.filter(pk=raw_permission)
                .select_related("cost_center")
                .first()
            )
        except (ValueError, ValidationError):
            permission = None
        if permission:
            initial["cost_center"] = permission.cost_center_id
        return initial

    def form_valid(self, form):
        uploaded = form.cleaned_data["file"]
        document_content = form.canonical
        bbox = canonical.compute_bbox(document_content) or (None, None, None, None)

        with uploaded_file_cleanup() as state, transaction.atomic():
            plan = GeoPlan.objects.create(
                title=form.cleaned_data["title"],
                cost_center=form.cleaned_data["cost_center"],
                flight_permission=form.cleaned_data.get("flight_permission"),
                created_by=self.request.user,
                status="draft",
            )
            doc_type, _created = DocumentType.objects.get_or_create(
                code=GEO_SOURCE_DOC_TYPE_CODE,
                defaults={
                    "name": GEO_SOURCE_DOC_TYPE_NAME,
                    "requires_expiry": False,
                },
            )
            document = Document(
                doc_type=doc_type,
                content_type=ContentType.objects.get_for_model(GeoPlan),
                object_id=plan.pk,
                title=uploaded.name,
                issue_date=timezone.localdate(),
                file_path="",
            )
            document.save()
            # Set only after the storage write so a later failure in this block
            # removes the orphaned file (uploaded_file_cleanup).
            state["path"] = save_uploaded_file(document, uploaded)

            version = GeoPlanVersion.objects.create(
                plan=plan,
                version_number=1,
                content=document_content,
                content_checksum=canonical.canonical_checksum(document_content),
                source="import",
                feature_count=canonical.count_features(document_content),
                size_bytes=canonical.size_bytes(document_content),
                bbox_west=bbox[0],
                bbox_south=bbox[1],
                bbox_east=bbox[2],
                bbox_north=bbox[3],
                created_by=self.request.user,
            )
            plan.source_document = document
            plan.current_version = version
            plan.save(
                update_fields=["source_document", "current_version", "updated_at"]
            )
            set_audit_context(
                self.request,
                plan,
                action="geo_plan_imported",
                metadata={"version": 1, "features": version.feature_count},
            )
        self._plan = plan
        return redirect("geo-plan-detail", pk=plan.pk)


# ── GEO-9: status workflow ────────────────────────────────────────────────
# draft → editing → in_review → approved | rejected, with rejected → editing and
# approved → editing (un-approving needs the approve permission). Each view is a
# StatusTransitionView; the shared status-change signal writes GeoPlanHistory.


class GeoPlanStartEditing(StatusTransitionView):
    model = GeoPlan
    permission_action = "change"
    target_status = "editing"
    valid_from_statuses = ["draft"]
    success_message = gettext_lazy("Editing started.")


class GeoPlanSubmitReview(StatusTransitionView):
    model = GeoPlan
    permission_action = "change"
    target_status = "in_review"
    valid_from_statuses = ["editing"]
    success_message = gettext_lazy("Plan submitted for review.")


class GeoPlanApprove(StatusTransitionView):
    model = GeoPlan
    permission_action = "approve"
    target_status = "approved"
    valid_from_statuses = ["in_review"]
    success_message = gettext_lazy("Plan approved.")


class GeoPlanReject(StatusTransitionView):
    model = GeoPlan
    permission_action = "approve"
    target_status = "rejected"
    valid_from_statuses = ["in_review"]
    success_message = gettext_lazy("Plan rejected.")


class GeoPlanResumeEditing(StatusTransitionView):
    model = GeoPlan
    permission_action = "change"
    target_status = "editing"
    valid_from_statuses = ["rejected"]
    success_message = gettext_lazy("Editing resumed.")


class GeoPlanReopen(StatusTransitionView):
    model = GeoPlan
    permission_action = "approve"
    target_status = "editing"
    valid_from_statuses = ["approved"]
    success_message = gettext_lazy("Plan reopened for editing.")


class WeatherReviewCreate(ModelPermissionRequiredMixin, View):
    """R8.1: put the meteorological review on record (ISO 8.1).

    POST only, and only from the plan's own page: this records that a person
    reviewed the conditions, so it must be an act, not a side effect of
    rendering. The numbers are stored as read -- a forecast cannot be looked up
    again after the fact (the provider answers a later model run, or refuses a
    past date), so a row pointing back at the provider would be evidence of
    nothing.
    """

    model = WeatherReview
    permission_action = "add"

    def post(self, request, pk):
        from apps.core.weather import bbox_centroid, forecast_for

        plan = get_object_or_404(GeoPlan, pk=pk)
        centroid = bbox_centroid(plan.current_version)
        permission = plan.flight_permission
        target_date = permission.valid_from if permission else None
        if centroid is None or target_date is None:
            messages.error(
                request,
                _("This plan has no area or no linked permit date to review."),
            )
            return redirect(plan.get_absolute_url())

        latitude, longitude = centroid
        forecast = forecast_for(latitude, longitude, target_date)
        if forecast is None:
            # Deliberately not a blank row: "we asked and got nothing" is not a
            # meteorological review, and filing it as one would be worse than
            # having none.
            messages.error(
                request,
                _("The forecast is unavailable right now, so nothing was recorded."),
            )
            return redirect(plan.get_absolute_url())

        review = WeatherReview.from_forecast(
            plan=plan,
            forecast=forecast,
            latitude=latitude,
            longitude=longitude,
            user=request.user,
        )
        set_audit_context(request, review)
        review.save()
        messages.success(request, _("Weather review recorded."))
        return redirect(plan.get_absolute_url())
