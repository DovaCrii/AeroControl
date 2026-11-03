"""Seed the DocumentType catalog for a DGAC RPAS operation (LV-1).

Idempotent by `code` (get_or_create): safe to run more than once, and a rerun
after a name is edited in the UI leaves that edit alone -- it only fills in
codes that are still missing. See docs/compliance-setup.md.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import DocumentType

# LV-95: the category is part of the catalog definition, not an afterthought --
# a type seeded without one lands under "Other", which is exactly what the
# grouping exists to avoid. `test_the_seeded_catalog_leaves_nothing_under_other`
# (test_lv94_lv95_upload_form.py) fails if any row here leaves it at the default.
PERSONNEL = DocumentType.CATEGORY_PERSONNEL
AIRCRAFT = DocumentType.CATEGORY_AIRCRAFT
DGAC = DocumentType.CATEGORY_DGAC
OPERATIONAL = DocumentType.CATEGORY_OPERATIONAL
MAINTENANCE = DocumentType.CATEGORY_MAINTENANCE
COMPANY = DocumentType.CATEGORY_COMPANY

# (code, name, requires_expiry, is_insurance, is_operational_record, category)
DOCUMENT_TYPES = [
    ("dgac-credential", "Credencial DGAC de operador", True, False, False, PERSONNEL),
    ("medical-cert", "Certificado de aptitud médica", True, False, False, PERSONNEL),
    # LV-121: `requires_expiry=False` desde el 2026-08-20, con el papel a la
    # vista. El "Certificado del Registro Nacional de RPA" que emite la DGAC
    # **no trae fecha de término**: es una inscripción —marca, modelo, serie,
    # propietario— y el propio documento aclara que "no constituye autorización
    # para operación del RPA", que es lo que sí caduca y vive en otros tipos.
    # Marcado como que la exige, el formulario rechazaba el PDF real y obligaba
    # a inventar un vencimiento; esa fecha inventada después habría generado una
    # alerta por algo que no vence. La migración `compliance/0023` lo corrige
    # también en las instalaciones existentes: el seed es idempotente por
    # `code`, así que por sí solo no toca una fila ya creada.
    (
        "aircraft-registration",
        "Certificado de inscripción RPA",
        False,
        False,
        False,
        AIRCRAFT,
    ),
    (
        "airworthiness-cert",
        "Certificado de aeronavegabilidad",
        True,
        False,
        False,
        AIRCRAFT,
    ),
    (
        "liability-insurance",
        "Póliza de responsabilidad civil",
        True,
        True,
        False,
        AIRCRAFT,
    ),
    # LV-117: la Resolución Exenta con que la **JAC** aprueba el seguro RPA --
    # el papel que cierra el ciclo que `Aircraft.insurance_status` modela
    # (`filed` -> `active`). No existía tipo para él, así que el respaldo de una
    # aeronave autorizada no tenía dónde vivir: la póliza y su certificado se
    # cargaban como `liability-insurance` y la resolución que los aprueba, en
    # ninguna parte.
    #
    # Va en AIRCRAFT y no en DGAC a propósito: la JAC no es la DGAC (esa
    # categoría es de presentaciones y autorizaciones DGAC), y quien busca este
    # papel lo busca junto al seguro de la aeronave, que es de lo que habla.
    #
    # requires_expiry=True -- la resolución trae "TÉRMINO DE VIGENCIA" y caduca
    # con la póliza que aprueba. is_insurance=False: esa bandera pinta la
    # columna de seguro de la lista de aeronaves, y desde LV-29 la fecha
    # canónica es `Aircraft.insurance_expiry`; marcar un segundo tipo pondría
    # dos documentos compitiendo por la misma columna (gana el que venza antes).
    (
        "jac-insurance-approval",
        "Resolución JAC que aprueba el seguro",
        True,
        False,
        False,
        AIRCRAFT,
    ),
    # LV-121: la otra mitad del trámite. Mismo par que `LV-64` separó para la
    # DGAC —la carta que va, la autorización que vuelve—: este es el formulario
    # "Solicitud de aprobación de seguros para operaciones con RPA" que se manda
    # a `segurosjac@jac.gob.cl`, y `jac-insurance-approval` es la resolución que
    # contesta. Tenerlos juntos es lo que permite ver que una solicitud sigue
    # sin respuesta, que es exactamente el estado `filed` de
    # `Aircraft.insurance_status` (LV-81).
    #
    # requires_expiry=False: una solicitud no vence, ocurrió. Mismo criterio que
    # `flight-request` y los registros operacionales.
    (
        "jac-insurance-request",
        "Solicitud de aprobación de seguro a la JAC",
        False,
        False,
        False,
        AIRCRAFT,
    ),
    # LV-230: **renombrado, porque el nombre viejo hizo inventar un tipo
    # duplicado.**
    #
    # Se llamaba "Autorización DGAC (carta de permiso)" mientras el comentario de
    # `LV-64` decía que es *"lo que va **hacia** la DGAC como parte de la
    # solicitud"* — el nombre y la documentación se contradecían. Leyendo el
    # nombre, "carta de permiso" parecía un papel **de** la DGAC, así que `LV-225`
    # creó `client-authorization-letter` para la carta del mandante sin ver que
    # era este mismo documento. Confirmado con el usuario: **son el mismo papel.**
    #
    # El daño no fue teórico: el expediente pedía los dos, el usuario subió el
    # mismo PDF dos veces, y la bandeja mostró dos alertas por un solo hecho.
    #
    # ⚠️ **El `code` no se toca.** Dice "dgac" para algo que no es de la DGAC, y
    # eso chirría — pero es la llave con la que están guardados los documentos de
    # producción y con la que lo buscan los tests. Cambiarlo obligaría a una
    # migración de datos por una mejora cosmética de un identificador interno. Lo
    # que la gente lee es el nombre, y el nombre ya dice la verdad.
    (
        "dgac-flight-permit",
        "Carta del mandante",
        False,
        False,
        False,
        DGAC,
    ),
    # LV-64: two distinct real documents, not one -- the letter above is what
    # goes *to* the DGAC as part of the request; this is what comes *back*,
    # signed and folio'd, once the DGAC actually approves the operation
    # ("Autorización de Operación RPA" in the DGAC's own wording). Approving a
    # permission in the app now requires this one (see
    # FlightPermissionApprove), not the letter -- only the signed
    # authorization actually certifies DGAC approval.
    (
        "dgac-rpa-operation-authorization",
        "Autorización de operación RPA",
        True,
        False,
        False,
        DGAC,
    ),
    # LV-230: acá vivía `client-authorization-letter`, que `LV-225` creó para la
    # carta del mandante sin ver que `dgac-flight-permit` (arriba) ya era ese
    # papel. Se retira y sus documentos se trasladan en `compliance.0025`.
    #
    # De esa fila sobrevive una decisión que sigue valiendo y por eso se mudó
    # arriba: **`requires_expiry=False`**. El informe quiere reportar cartas por
    # vencer (`SPEC_REPORTE_MENSUAL_RPA.md` §3), lo que invita a marcarlo `True`,
    # pero no toda carta trae plazo escrito y exigir la fecha obligaría a
    # **inventarla** para poder cargar el papel — el mal que `LV-219` quitó del
    # alta del permiso. Nótese que el tipo de arriba decía `True`: eso quedaba de
    # cuando se creía que era una autorización de la DGAC, que sí vence.
    #
    # LV-30: the per-flight operational records. They do not expire (a record of
    # what happened, not a validity), so requires_expiry=False.
    ("flight-log", "Bitácora de vuelo", False, False, True, OPERATIONAL),
    # LV-290: el **registro de vuelo `.TXT`** que el portal de la DGAC pide adjuntar
    # al registrar las operaciones de una solicitud. No es la bitácora de arriba
    # (el formulario interno REG-015): es el archivo técnico que genera el control
    # del RPA, y va a la DGAC. Categoría DGAC —es lo que se presenta ante ella— y
    # `is_operational_record=False`: esa bandera lo contaría en el cierre mensual
    # como un registro operacional más, y no lo es. No vence (ocurrió).
    # La migración `compliance/0027` lo crea también donde el sembrado ya corrió.
    ("flight-log-txt", "Archivo de registro de vuelo", False, False, False, DGAC),
    ("rpa-checklist", "Lista de chequeo RPA", False, False, True, OPERATIONAL),
    (
        "drone-inspection",
        "Inspección de RPA",
        False,
        False,
        True,
        OPERATIONAL,
    ),
    # R4.1/R4.8: pulled forward from R4.8 because import_document_repository
    # cannot classify anything under the Z: repository's "02.-"/"03.-"/"04.-"
    # subfolders without them. Historical records, not validities that lapse
    # -- requires_expiry=False, same reasoning as the flight-log group above.
    ("flight-request", "Solicitud de vuelo presentada", False, False, False, DGAC),
    (
        "incident-investigation-record",
        "Investigación de incidente",
        False,
        False,
        False,
        OPERATIONAL,
    ),
    (
        "maintenance-certificate",
        "Certificado de mantención",
        False,
        False,
        False,
        MAINTENANCE,
    ),
    # LV-383: el papel con que un taller recibe un equipo (o su cotización): cuelga
    # de la mantención que registra el ingreso a servicio técnico. Es un hecho que
    # ocurrió, no una vigencia -- requires_expiry=False.
    (
        "workshop-intake-receipt",
        "Recepción en servicio técnico",
        False,
        False,
        False,
        MAINTENANCE,
    ),
    # R7.3 (ISO 7.1.5): GNSS/RTK and camera calibration certificates. A real
    # "Certificado Calibración.pdf" already sits in Z:\CC706-...\04.- Mantenciones
    # waiting for a place to live. requires_expiry=True -- unlike
    # maintenance-certificate above, ISO 7.1.5 asks for a *vigente* one, so a
    # lapsed calibration should watch and alert like airworthiness-cert does.
    (
        "calibration-certificate",
        "Certificado de calibración",
        True,
        False,
        False,
        MAINTENANCE,
    ),
    # R4.6/R4.8: the remaining company-wide document types the new "Documentos
    # de la empresa" repository needs to actually be usable -- without these,
    # nobody could classify an AOC or a procedure upload there at all.
    # aoc-certificate: confirmed with the user 2026-08-11 -- unlike a DGAC
    # credential or an insurance policy, the AOC is a single internal
    # document that is not periodically renewed/re-uploaded.
    # requires_expiry=False, same reasoning as company-procedure below (a
    # static reference document, not a vigencia to watch).
    ("aoc-certificate", "Certificado AOC", False, False, False, COMPANY),
    # company-procedure: manuals and procedures (e.g. the flyaway/emergency
    # response procedure ISO 45001 8.2 asks for). Revised through
    # is_current_version, not a vigencia -- same reasoning as
    # maintenance-certificate above.
    (
        "company-procedure",
        "Procedimiento o manual",
        False,
        False,
        False,
        COMPANY,
    ),
    # monthly-non-operation-notice: the DGAC filing for a month with no RPAS
    # activity. A historical record of what (did not) happen, not a validity.
    (
        "monthly-non-operation-notice",
        "Aviso mensual de no operación",
        False,
        False,
        False,
        DGAC,
    ),
]


# LV-385: la guía de cada tipo -- {code: (description, reference_code, sort_order)}.
# Va aparte de la tupla de arriba (cuya forma no cambia) y es **dato en español**,
# no un msgid: no pasa por gettext. `sort_order` es único dentro de su categoría y
# sigue el orden en que cada sección se lee. Es el mismo contenido que lleva la
# migración `compliance/0028`; un guardián los cruza.
DOCUMENT_TYPE_GUIDE = {
    "dgac-credential": ("Habilita al piloto; vence", "", 10),
    "medical-cert": ("Acredita la aptitud médica del piloto; vence", "", 20),
    "aircraft-registration": (
        "Inscripción DGAC; no vence ni autoriza a operar",
        "",
        10,
    ),
    "airworthiness-cert": (
        "Acredita que la aeronave está en condiciones de volar; vence",
        "",
        20,
    ),
    "liability-insurance": ("Cubre los daños a terceros; vence", "", 30),
    "jac-insurance-request": (
        "Se envía a la JAC para que apruebe el seguro; no vence",
        "",
        40,
    ),
    "jac-insurance-approval": ("Respuesta de la JAC; vence con la póliza", "", 50),
    "dgac-flight-permit": ("La firma el cliente; acompaña la solicitud", "", 10),
    "dgac-rpa-operation-authorization": (
        "La entrega la DGAC al aprobar la operación; vence",
        "",
        20,
    ),
    "flight-log-txt": ("El archivo que pide el portal DGAC", ".TXT", 30),
    "flight-request": ("Solicitud ya presentada ante la DGAC; no vence", "", 40),
    "monthly-non-operation-notice": (
        "Se presenta a la DGAC el mes en que no hubo operación",
        "",
        50,
    ),
    "flight-log": ("Registro interno de cada vuelo realizado", "REG-015", 10),
    "rpa-checklist": ("Verificación del RPA antes del vuelo", "LVE-003", 20),
    "drone-inspection": ("Revisión del estado del RPA", "LVE-002", 30),
    "incident-investigation-record": (
        "Análisis de un incidente y de sus causas",
        "",
        40,
    ),
    "maintenance-certificate": ("Respalda una mantención realizada; no vence", "", 10),
    "calibration-certificate": (
        "GNSS/RTK/cámara; la norma exige que esté vigente",
        "",
        20,
    ),
    "workshop-intake-receipt": (
        "Respalda el ingreso de un equipo a un taller; no vence",
        "",
        30,
    ),
    "aoc-certificate": ("Documento único de la empresa; no se renueva", "", 10),
    "company-procedure": (
        "Procedimientos y manuales; se revisan por versión",
        "",
        20,
    ),
}


class Command(BaseCommand):
    help = "Create the standard DocumentType catalog for a DGAC RPAS operation."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for (
            code,
            name,
            requires_expiry,
            is_insurance,
            is_op_record,
            category,
        ) in DOCUMENT_TYPES:
            obj, created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "requires_expiry": requires_expiry,
                    "is_insurance": is_insurance,
                    "is_operational_record": is_op_record,
                    "category": category,
                },
            )
            created_count += int(created)
            # LV-385: la guía sólo llena lo que está vacío -- lo editado desde la
            # interfaz se respeta, igual que el nombre.
            description, reference_code, sort_order = DOCUMENT_TYPE_GUIDE[code]
            changed = []
            if not obj.description:
                obj.description = description
                changed.append("description")
            if not obj.reference_code and reference_code:
                obj.reference_code = reference_code
                changed.append("reference_code")
            if not obj.sort_order:
                obj.sort_order = sort_order
                changed.append("sort_order")
            if changed:
                obj.save(update_fields=[*changed, "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(DOCUMENT_TYPES)} document types "
                f"({created_count} created)."
            )
        )
