"""LV-158: la prueba interna de conocimientos — banco, sorteo y corrección.

Pedido del usuario: *"una prueba interna para ver las capacidades […] al operador
quedar en el historial […] con un aprobado o insuficiente, y en qué se equivocó,
qué reforzar […] para conocer y dejar claro cómo está la condición de los
profesionales"*.

**El banco es dato, no código** (`data/rpas_knowledge_bank.json`, material propio
de J.E.J.): corregir una redacción o agregar preguntas no debería exigir tocar
Python ni desplegar. Misma decisión que el catálogo del AIP en `R10.7`.

**La corrección es del lado del servidor y el intento guarda su propia copia de
lo preguntado.** Las dos mitades importan: si la respuesta correcta viajara al
navegador, la prueba no mediría nada; y si el intento sólo guardara el puntaje,
editar el banco reescribiría lo que alguien rindió el año pasado — que es
exactamente el error que `WeatherReview` evita guardando los números tal como se
leyeron.

Las reglas las fijó el usuario el 2026-08-26 y por eso son constantes con nombre,
no literales sueltos: **25 preguntas, 80% para aprobar, vigencia de 12 meses.**
"""

import json
import random
from functools import lru_cache
from pathlib import Path

from django.utils.translation import gettext_lazy as _

# Decisiones del usuario, 2026-08-26. AGENTS.md: un umbral inventado convierte un
# control en un estorbo que alguien desactiva, así que estos tres números son
# suyos y viven acá para que un test pueda nombrarlos.
QUESTIONS_PER_ATTEMPT = 25
PASS_PERCENT = 80
VALID_MONTHS = 12

BANK_PATH = Path(__file__).resolve().parent / "data" / "rpas_knowledge_bank.json"


def _unwrapped(text):
    """El texto con los espacios colapsados, **sin cambiar una sola palabra**.

    LV-163: el banco se extrajo de un documento de la DGAC y trae los saltos de
    línea de ese PDF metidos a mitad de frase ("PREVIO AL INICIO DE UN VUELO
    SERÁ RESPONSABILIDAD DEL\\nOPERADOR DE UN RPA…"). En pantalla eso cortaba
    los renglones en puntos arbitrarios, sin relación con el ancho de la caja, y
    era la mitad de por qué la prueba se leía plana.

    Colapsar espacios es la **única** normalización que se le hace al banco, y
    por eso: no toca ninguna palabra. Bajar las mayúsculas sería lo obvio y está
    descartado a propósito — el banco lleva `METAR SCVD 211400Z 12003KT 4000
    VCFG BKN020 04/03 Q1026=`, `DAN 151`, `RPA`, `DGAC`, y un normalizador que
    les baje la caja le cambia el sentido a una pregunta de examen. La fidelidad
    al documento de la DGAC es lo que hace que la prueba valga; el remedio para
    que se lea bien es tipográfico, no textual.
    """
    return " ".join(text.split())


@lru_cache(maxsize=1)
def _bank():
    """El banco completo, leído una vez por proceso.

    `lru_cache` y no una constante de módulo: así el archivo no se lee al
    importar (los comandos y las migraciones no lo necesitan) y un test puede
    limpiar la caché si quiere sustituirlo.

    Los espacios se colapsan **acá y una sola vez**, así que todo lo que sale de
    este módulo —lo que se muestra, lo que se corrige y la copia que se archiva
    en `answers`— ve el mismo texto. Normalizar en la plantilla habría dejado la
    copia archivada con los saltos del PDF adentro.
    """
    payload = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    return [
        {
            **question,
            "text": _unwrapped(question["text"]),
            "options": [
                {**option, "text": _unwrapped(option["text"])}
                for option in question["options"]
            ],
        }
        for question in payload["questions"]
    ]


def bank_size():
    return len(_bank())


def bank_source():
    """La procedencia declarada dentro del propio archivo de datos."""
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))["source"]


def draw_questions(count=QUESTIONS_PER_ATTEMPT, seed=None):
    """`count` preguntas al azar, **sin la respuesta correcta**.

    Lo que sale de acá es lo que se le muestra a la persona, así que la clave
    correcta no viaja: se resuelve al corregir, contra el banco. Es la diferencia
    entre una prueba y un formulario.

    `seed` existe sólo para los tests: una prueba que sortea distinto en cada
    corrida no se puede afirmar.

    El sorteo real usa `SystemRandom`, y no por criptografía: es lo que hace que
    dos personas rindiendo a la vez no reciban el mismo juego, y que el juego no
    se pueda anticipar mirando el reloj. La rama con semilla es determinista **a
    propósito** y sólo la alcanzan los tests.

    `nosec B311`: lo que bandit marca es usar `random` donde hace falta
    imprevisibilidad garantizada —tokens, contraseñas—. Acá se barajan preguntas
    de un banco que la propia persona puede leer completo si quiere: la
    aleatoriedad reparte, no protege. Mismo caso que el barajado de Welzl en
    `apps/geo/enclosing.py`.
    """
    chooser = random.Random(seed) if seed is not None else random.SystemRandom()  # nosec B311
    drawn = chooser.sample(_bank(), min(count, bank_size()))
    return [
        {"id": question["id"], "text": question["text"], "options": question["options"]}
        for question in drawn
    ]


def grade(question_ids, given):
    """Corregir un intento. Devuelve `(filas, correctas, porcentaje, aprobado)`.

    `filas` es la copia que el intento guarda: cada pregunta con su enunciado,
    sus opciones, lo que la persona marcó y lo que correspondía. Es lo que
    después responde *"en qué se equivocó, qué reforzar"* sin depender de que el
    banco no haya cambiado.

    Una pregunta sin responder cuenta como incorrecta y se dice (`given: ""`), no
    se descuenta del total: el total es lo que se preguntó.
    """
    by_id = {question["id"]: question for question in _bank()}
    rows = []
    for question_id in question_ids:
        question = by_id.get(question_id)
        if question is None:
            # Una pregunta que ya no está en el banco: se conserva la marca para
            # que el total no cambie de forma silenciosa, y se dice que no se
            # pudo corregir en vez de contarla como buena.
            rows.append(
                {
                    "id": question_id,
                    "text": str(_("This question is no longer in the bank.")),
                    "options": [],
                    "given": given.get(question_id, ""),
                    "answer": "",
                    "correct": False,
                }
            )
            continue
        answered = given.get(question["id"], "")
        rows.append(
            {
                "id": question["id"],
                "text": question["text"],
                "options": question["options"],
                "given": answered,
                "answer": question["answer"],
                "correct": answered == question["answer"],
            }
        )
    correct = sum(1 for row in rows if row["correct"])
    total = len(rows) or 1
    percent = round(correct * 100 / total, 1)
    return rows, correct, percent, percent >= PASS_PERCENT


def label_for(option_key, options):
    """El texto de una opción por su clave, para mostrar lo marcado en la revisión."""
    for option in options:
        if option["key"] == option_key:
            return option["text"]
    return ""


def valid_until(taken_on):
    """La fecha en que el resultado deja de estar vigente: `VALID_MONTHS` después.

    Doce meses a mano y no con `dateutil`: el proyecto tiene política de
    dependencias mínimas y el gate corre `pip-audit`, así que una librería entera
    para sumar meses no se justifica. El 29 de febrero cae al 28: la alternativa
    —el 1 de marzo— alargaría la vigencia un día, y de las dos formas de
    equivocarse por un día conviene la que no regala vigencia.
    """
    import calendar

    months = taken_on.month - 1 + VALID_MONTHS
    year = taken_on.year + months // 12
    month = months % 12 + 1
    day = min(taken_on.day, calendar.monthrange(year, month)[1])
    return taken_on.replace(year=year, month=month, day=day)


def bank_is_available():
    """Si el archivo de datos está y se puede leer.

    La pantalla no debería reventar porque falte un archivo de datos: sin banco
    no hay prueba que rendir, y eso se dice.
    """
    try:
        return bank_size() > 0
    except (OSError, ValueError, KeyError):  # pragma: no cover - archivo ausente
        return False
