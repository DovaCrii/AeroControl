"""LV-368 fase 3: leer la credencial DGAC de un operador desde su PDF con texto.

Pedido del usuario: *"si tú la subes, que saque la información necesaria y la
complemente"*. Este módulo **propone, nunca escribe**: `credential_from_text` devuelve,
por campo, una `Proposal` con su valor, su confianza y el fragmento del que salió, y
quien llama decide. Misma regla que el folio del permiso (LV-231): un valor
equivocado escrito solo es peor que un campo en blanco, porque el equivocado nadie lo
revisa.

Criterio de confianza:

- `exact`: **un solo** candidato (tras normalizar) y una **etiqueta reconocida** («N°
  Credencial», «Fecha de emisión», «Vencimiento»/«Vigencia», «Clase»/«Categoría»,
  «Restricciones», titular).
- `doubtful`: un solo candidato, pero bajo una etiqueta laxa («Válido hasta», «Emisión»,
  «N°»...).
- **Sin propuesta**: dos candidatos distintos, o una fecha que no existe en el
  calendario. Ahí no hay una respuesta, hay dudas.

⚠️ No se pudo ver una credencial real: las etiquetas son las que la persona describió y
las pruebas usan un PDF sintético. Cuando llegue un ejemplo anonimizado hay que
confirmar estas etiquetas contra él.

⚠️ **Privacidad.** El RUT y el titular se leen **solo para compararlos** con la ficha
(`Operator.rut`, `Operator.full_name`). Sus propuestas llevan como fragmento el nombre
de la etiqueta, nunca el valor, y ningún fragmento se arma con la línea completa del
PDF: se reconstruye como «etiqueta: valor» del propio campo, para que un RUT o un nombre
de otra línea no se cuelen en un fragmento ajeno.
"""

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from apps.core.pdf_text import text_from_pdf

logger = logging.getLogger(__name__)

EXACT = "exact"
DOUBTFUL = "doubtful"

FRAGMENT_MAX = 60

# Campos que se leen. `rut` y `holder` son solo para comparar.
NUMBER = "number"
ISSUE_DATE = "issue_date"
EXPIRY_DATE = "expiry_date"
CLASS_ = "credential_class"
RESTRICTIONS = "restrictions"
HOLDER = "holder"
RUT = "rut"

# Los tres que se pueden guardar en la ficha; el resto es informativo o de cotejo.
WRITABLE_FIELDS = (NUMBER, ISSUE_DATE, EXPIRY_DATE)
COMPARE_ONLY_FIELDS = (HOLDER, RUT)


@dataclass(frozen=True)
class Proposal:
    value: object
    confidence: str
    fragment: str


# Etiquetas por campo, escritas **sin tildes y en minúscula** (se compara contra el
# texto normalizado del mismo modo). `strong` da `exact`; `weak` solo `doubtful`.
LABELS = {
    NUMBER: {
        "strong": [
            r"n[o°º.]*\s*(?:de\s+)?credencial",
            r"credencial\s*n[o°º.]*",
            r"numero\s+(?:de\s+)?credencial",
        ],
        "weak": [r"n[o°º]\.?", r"numero", r"licencia\s*n[o°º.]*"],
    },
    ISSUE_DATE: {
        "strong": [
            r"fecha\s+(?:de\s+)?(?:emision|expedicion)",
        ],
        "weak": [r"emision", r"emitid[ao](?:\s+el)?", r"expedid[ao](?:\s+el)?"],
    },
    EXPIRY_DATE: {
        "strong": [
            r"fecha\s+(?:de\s+)?vencimiento",
            r"vencimiento",
            r"vigencia(?:\s+hasta)?",
            r"vigente\s+hasta",
        ],
        "weak": [r"valid[ao]\s+hasta", r"expira(?:cion)?", r"fecha\s+de\s+expiracion"],
    },
    CLASS_: {
        "strong": [r"clase", r"categoria"],
        "weak": [],
    },
    RESTRICTIONS: {
        "strong": [r"restricci(?:on|ones)"],
        "weak": [],
    },
    HOLDER: {
        "strong": [r"titular", r"nombre\s+del\s+titular"],
        "weak": [r"nombres?"],
    },
    RUT: {
        "strong": [r"r\.?\s?u\.?\s?t\.?", r"run"],
        "weak": [],
    },
}

_SEPARATOR = r"[ \t]*[:\-–]?[ \t]*"

_COMPILED = {
    field: {
        tier: [re.compile(rf"^(?P<label>{p})\b{_SEPARATOR}(?P<rest>.*)$") for p in pats]
        for tier, pats in tiers.items()
    }
    for field, tiers in LABELS.items()
}

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# dd/mm/aaaa, dd-mm-aaaa, dd.mm.aaaa
_DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?!\d)")
# aaaa-mm-dd
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
# 15 de marzo de 2024
_DATE_LONG = re.compile(
    r"(?<!\d)(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+|del\s+)?(\d{4})(?!\d)"
)

_RUT_TEXT = re.compile(r"(?<![\dA-Za-z])\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK](?![\dA-Za-z])")

_NUMBER_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9./\-]{1,28}")


def _plain(text):
    """Sin tildes ni caja, **conservando el largo** (para cortar el original)."""
    out = []
    for char in text:
        decomposed = "".join(
            c
            for c in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(c)
        )
        lowered = decomposed.lower() if len(decomposed) == 1 else char.lower()
        out.append(lowered if len(lowered) == 1 else char)
    return "".join(out)


def _dates_in(text):
    """`(fechas válidas, hubo alguna inválida)` en el texto, sin repetir."""
    found, invalid = [], False
    plain = _plain(text)
    for day, month, year in (
        [m.groups() for m in _DATE_DMY.finditer(plain)]
        + [(m[3], m[2], m[1]) for m in _DATE_ISO.finditer(plain)]
        + [(m[1], str(_MONTHS.get(m[2], 0)), m[3]) for m in _DATE_LONG.finditer(plain)]
    ):
        try:
            value = date(int(year), int(month), int(day))
        except ValueError:
            invalid = True
            continue
        if value not in found:
            found.append(value)
    return found, invalid


def _label_in(line, tiers):
    """`(nivel, etiqueta tal como está en el PDF, resto de la línea)` o `None`."""
    plain = _plain(line.strip())
    stripped = line.strip()
    for tier in ("strong", "weak"):
        for pattern in tiers[tier]:
            match = pattern.match(plain)
            if match:
                return (
                    tier,
                    stripped[: match.end("label")].strip(),
                    (stripped[match.start("rest") :].strip()),
                )
    return None


def _any_label(line):
    return any(_label_in(line, tiers) is not None for tiers in _COMPILED.values())


def _fragment(label, value):
    return f"{label}: {value}"[:FRAGMENT_MAX]


def credential_from_text(text):
    """`{campo: Proposal}` para lo que el texto permite afirmar; vacío si nada.

    Nunca levanta: un texto raro devuelve menos campos, no un error.
    """
    lines = [line for line in (text or "").splitlines()]
    proposals = {}
    for field in LABELS:
        proposal = _propose(field, lines)
        if proposal is not None:
            proposals[field] = proposal
    return proposals


def _candidates(field, lines):
    """Candidatos crudos `[(nivel, etiqueta, valor)]` y si alguno vino roto."""
    tiers = _COMPILED[field]
    out, broken = [], False
    for index, line in enumerate(lines):
        hit = _label_in(line, tiers)
        if hit is None:
            continue
        tier, label, rest = hit
        # Etiqueta sola en su línea: el valor es la siguiente línea con contenido
        # (así sale una tabla de dos columnas en `pypdf`), salvo que esa línea sea a
        # su vez otra etiqueta.
        if not rest:
            for follower in lines[index + 1 : index + 3]:
                if follower.strip():
                    if not _any_label(follower):
                        rest = follower.strip()
                    break
        if not rest:
            continue
        if field in (ISSUE_DATE, EXPIRY_DATE):
            dates, invalid = _dates_in(rest)
            broken = broken or invalid
            out.extend((tier, label, value) for value in dates)
        elif field == NUMBER:
            token = _NUMBER_TOKEN.match(rest)
            if token and any(ch.isdigit() for ch in token.group(0)):
                out.append((tier, label, token.group(0).strip("./-")))
        elif field == RUT:
            ruts = _RUT_TEXT.findall(rest)
            out.extend((tier, label, rut) for rut in ruts)
            broken = broken or (not ruts and bool(rest))
        elif field == HOLDER:
            out.append((tier, label, " ".join(rest.split())))
        else:  # clase y restricciones: el texto de la línea, acotado
            out.append((tier, label, " ".join(rest.split())[:120]))
    return out, broken


def _key(field, value):
    if field == RUT:
        from .rut import normalize_rut

        return normalize_rut(value)
    if isinstance(value, str):
        return _plain(" ".join(value.split()))
    return value


def _propose(field, lines):
    found, broken = _candidates(field, lines)
    if broken or not found:
        return None
    distinct = {_key(field, value) for _tier, _label, value in found}
    if len(distinct) != 1:
        return None
    strong = [hit for hit in found if hit[0] == "strong"]
    tier, label, value = (strong or found)[0]
    if field in (HOLDER, RUT):
        fragment = label[:FRAGMENT_MAX]
    else:
        fragment = _fragment(
            label, value.isoformat() if isinstance(value, date) else value
        )
    return Proposal(
        value=value,
        confidence=EXACT if strong else DOUBTFUL,
        fragment=fragment,
    )


def credential_from_pdf(stream):
    """Lo mismo, desde un PDF. `None` si no hay texto que leer (foto, escaneo, roto).

    Distingue «no se pudo leer» (`None`) de «se leyó y no se afirma nada» (`{}`): la
    pantalla dice cosas distintas en cada caso. El log dice solo
    `credential_unreadable`, sin contenido.
    """
    text = text_from_pdf(stream)
    if text is None:
        logger.info("credential_unreadable")
        return None
    return credential_from_text(text)


def credential_from_bytes(data, extension):
    """Lector tolerante para un archivo ya guardado: solo se intenta con PDF."""
    if extension.lower() != "pdf":
        logger.info("credential_unreadable")
        return None
    return credential_from_pdf(io.BytesIO(data))
