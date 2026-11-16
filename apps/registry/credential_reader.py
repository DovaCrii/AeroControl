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
    # El formato numerado de la DGAC, cuando está, manda sobre las etiquetas sueltas.
    proposals.update(_dgac_layout(lines, text or ""))
    return proposals


# LV-448: el formato REAL de la credencial DGAC (visto el 2026-11-16 en credenciales
# reales, sin copiar ningún dato al repositorio) es el de una licencia OACI: cada campo
# va precedido de un número romano, en español e inglés. Las etiquetas genéricas de
# arriba no lo leían: el prefijo «III)» impedía reconocer «Nº», el titular no lleva
# rótulo, el RUT queda varias líneas debajo de «RUT / PASSPORT» y la emisión se llama
# «FECHA OTORGAMIENTO / DATE ISSUED», con la fecha en la línea siguiente.
#   III) Nº <número>                          → número de credencial
#   IV) <nombre> (a veces sigue en la línea siguiente) → titular
#   XIV) Validez Certificado / Certificate Validity <fecha> → vencimiento
#   FECHA OTORGAMIENTO / DATE ISSUED  ⏎ <fecha> → emisión
#   RUT / PASSPORT ... <un único RUT en el documento> → RUT
_ROMAN_FIELD = re.compile(r"^\s*(?P<num>[IVXL]{1,5})\)\s*(?P<rest>.*)$")
_ISSUED_LABEL = re.compile(r"fecha\s+(?:de\s+)?otorgamiento|date\s+issued")
_RUT_LABEL = re.compile(r"^\s*r\.?\s?u\.?\s?t\.?\s*/\s*passport")


def _dgac_layout(lines, text):
    """Propuestas del formato numerado de la DGAC; `{}` si el texto no lo tiene."""
    numbered = []
    for index, line in enumerate(lines):
        match = _ROMAN_FIELD.match(line)
        if match:
            numbered.append((match["num"], match["rest"].strip(), index))
    present = {num for num, _rest, _index in numbered}
    if "III" not in present or not ({"IV", "XIV"} & present):
        return {}
    out = {}

    numbers = [rest for num, rest, _index in numbered if num == "III"]
    if len(numbers) == 1:
        # Sobre el texto sin caja ni tildes («Nº» → «nº»), cortando el original.
        match = re.match(
            r"n[o°º.]*\s*(?P<value>[a-z0-9][a-z0-9./\-]*)", _plain(numbers[0])
        )
        if match and any(ch.isdigit() for ch in match["value"]):
            value = numbers[0][match.start("value") : match.end("value")].strip("./-")
            out[NUMBER] = Proposal(value, EXACT, _fragment("III) Nº", value))

    holders = [(rest, index) for num, rest, index in numbered if num == "IV"]
    if holders and holders[0][0] and not any(ch.isdigit() for ch in holders[0][0]):
        name, index = holders[0]
        confidence = EXACT
        follower = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if (
            follower
            and not _ROMAN_FIELD.match(follower)
            and not any(ch.isdigit() for ch in follower)
            and "/" not in follower
        ):
            name, confidence = f"{name} {follower}", DOUBTFUL
        out[HOLDER] = Proposal(" ".join(name.split()), confidence, "IV)")

    validity = [rest for num, rest, _index in numbered if num == "XIV"]
    if len(validity) == 1:
        dates, invalid = _dates_in(validity[0])
        if len(dates) == 1 and not invalid:
            out[EXPIRY_DATE] = Proposal(
                dates[0], EXACT, _fragment("XIV)", dates[0].isoformat())
            )

    for index, line in enumerate(lines):
        if _ISSUED_LABEL.search(_plain(line)):
            dates, invalid = _dates_in(" ".join(lines[index : index + 3]))
            if len(dates) == 1 and not invalid:
                out[ISSUE_DATE] = Proposal(
                    dates[0], EXACT, _fragment("DATE ISSUED", dates[0].isoformat())
                )
            break

    if any(_RUT_LABEL.match(_plain(line)) for line in lines):
        from .rut import normalize_rut

        ruts = {normalize_rut(rut): rut for rut in _RUT_TEXT.findall(text)}
        if len(ruts) == 1:
            out[RUT] = Proposal(next(iter(ruts.values())), EXACT, "RUT / PASSPORT")
    return out


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
