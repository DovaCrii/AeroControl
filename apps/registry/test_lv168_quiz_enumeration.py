"""LV-168: el enunciado que enumera se lee como enumeración, no como párrafo.

Regresión propia de `LV-163`. Al colapsar los espacios para sacar los saltos que
el PDF de la DGAC metía a mitad de frase, `_unwrapped` se llevó también los que
separaban los ítems `I.`/`II.`/`III.`. Seis preguntas del banco quedaron como un
párrafo corrido, y son justo aquellas cuyas opciones son "SÓLO I Y II" contra
"SÓLO II Y III": sin el corte hay que rastrear con el ojo dónde empieza cada ítem
para poder elegir.

Las propiedades que estos tests sostienen, y por qué cada una:

- **No se toca una sola palabra ni la caja.** Unir los renglones con un espacio
  reproduce el texto de entrada. Es la misma regla que `_unwrapped` ya se impuso:
  el banco lleva `METAR`, `DAN 151`, `RPA`, `DGAC`, y normalizar el texto de una
  pregunta de examen le cambia el sentido.
- **El disparo es conservador.** Con un solo marcador, o con marcadores fuera de
  orden, no se parte nada: un número romano puede aparecer en una frase sin ser
  una enumeración, y partir de más se lee como si faltara texto.
- **Se parte en presentación, no en el dato.** Lo que se corrige y la copia que
  el intento archiva siguen siendo la línea colapsada, así que los intentos ya
  rendidos también se benefician.
"""

import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template

from apps.registry import assessments

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
TAKE = Path(settings.BASE_DIR) / "templates" / "registry" / "assessment_take.html"


def _rule(selector):
    """El cuerpo de una regla de `app.css`, por selector exacto."""
    match = re.search(
        r"(?<![\w.-])" + re.escape(selector) + r"\s*\{(.*?)\}",
        CSS.read_text("utf-8"),
        re.DOTALL,
    )
    return match.group(1) if match else ""


CODIGO_AERONAUTICO = (
    "MENCIONE LAS SANCIONES ESTABLECIDAS EN EL CÓDIGO AERONÁUTICO, ART 185. "
    "I. AMONESTACIÓN ESCRITA. II. MULTAS DE 5 A 500 INGRESOS MÍNIMOS "
    "III. SUSPENSIÓN DE PERMISOS Y LICENCIAS HASTA POR 3 AÑOS "
    "IV. CANCELACIÓN DEFINITIVA DE PERMISOS O LICENCIAS"
)


def test_an_enumerated_question_becomes_one_line_per_item():
    lines = assessments.enumerated_lines(CODIGO_AERONAUTICO)

    assert len(lines) == 5
    assert lines[0] == (
        "MENCIONE LAS SANCIONES ESTABLECIDAS EN EL CÓDIGO AERONÁUTICO, ART 185."
    )
    assert lines[1] == "I. AMONESTACIÓN ESCRITA."
    assert lines[2] == "II. MULTAS DE 5 A 500 INGRESOS MÍNIMOS"
    assert lines[4] == "IV. CANCELACIÓN DEFINITIVA DE PERMISOS O LICENCIAS"


def test_not_a_single_word_or_letter_case_changes():
    lines = assessments.enumerated_lines(CODIGO_AERONAUTICO)

    assert " ".join(lines) == CODIGO_AERONAUTICO


def test_a_question_without_enumeration_is_left_whole():
    text = "¿CUÁL ES LA ALTURA MÁXIMA DE OPERACIÓN SEGÚN LA DAN 151?"

    assert assessments.enumerated_lines(text) == [text]


def test_a_lone_roman_numeral_does_not_split_the_question():
    """Un `I.` suelto no es una enumeración: hacen falta dos marcadores."""
    text = "SEGÚN EL ANEXO I. INDIQUE LA RESPUESTA CORRECTA"

    assert assessments.enumerated_lines(text) == [text]


def test_markers_out_of_sequence_do_not_split_the_question():
    """`II.` sin un `I.` antes no abre una enumeración."""
    text = "ALGO II. UNO III. OTRO"

    assert assessments.enumerated_lines(text) == [text]


def test_a_metar_is_never_mistaken_for_an_enumeration():
    """El banco lleva METAR crudo, con grupos que empiezan por números."""
    text = "METAR SCVD 211400Z 12003KT 4000 VCFG BKN020 04/03 Q1026="

    assert assessments.enumerated_lines(text) == [text]


def test_every_question_in_the_bank_survives_the_split_unchanged():
    """La propiedad, sobre el banco real y no sobre un ejemplo elegido."""
    split_questions = 0
    for question in assessments.draw_questions(count=assessments.bank_size(), seed=1):
        lines = assessments.enumerated_lines(question["text"])
        assert " ".join(lines) == question["text"]
        if len(lines) > 1:
            split_questions += 1
            assert lines[1].startswith("I.")

    assert split_questions >= 1, "el banco trae preguntas enumeradas: ver LV-168"


def test_the_filter_renders_one_element_per_line():
    """La plantilla es lo que arregla la pantalla; el filtro es su única puerta."""
    rendered = Template(
        "{% load assessment_extras %}"
        '{% for line in text|enumerated_lines %}<span class="quiz-text-line">'
        "{{ line }}</span>{% endfor %}"
    ).render(Context({"text": CODIGO_AERONAUTICO}))

    assert rendered.count('<span class="quiz-text-line">') == 5
    assert '<span class="quiz-text-line">I. AMONESTACIÓN ESCRITA.</span>' in rendered


def test_the_filter_leaves_a_plain_question_as_one_element():
    text = "¿QUÉ ES UN NOTAM?"

    rendered = Template(
        "{% load assessment_extras %}"
        '{% for line in text|enumerated_lines %}<span class="quiz-text-line">'
        "{{ line }}</span>{% endfor %}"
    ).render(Context({"text": text}))

    assert rendered.count('<span class="quiz-text-line">') == 1


# LV-168b: el enunciado se salía del recuadro. Un `<legend>` sin flotar es el
# "rendered legend" del navegador — se monta sobre el borde superior del
# `<fieldset>`, ignora su relleno y borra el borde por detrás. Medido en el
# navegador: sin flotar el enunciado arranca a **0 px** del borde de la caja;
# flotado, a los **21** que le corresponden (1 de borde + 20 de relleno). Con una
# línea apenas se notaba; con las seis de una pregunta enumerada la pregunta se
# ve suelta, fuera de su tarjeta. Estos dos tests son el guardián: el arreglo son
# dos piezas que sólo funcionan juntas, y separarlas devuelve el defecto.


def test_the_question_legend_keeps_floating_so_it_stays_inside_the_card():
    rule = _rule(".quiz-question")

    assert "float: left" in rule, (
        "un legend sin flotar se monta sobre el borde del fieldset y deja el "
        "enunciado fuera del recuadro: ver LV-168b"
    )
    assert "float: none" not in rule


def test_the_flex_lives_in_the_inner_row_and_not_in_the_legend():
    """El flex del número va adentro; en el `<legend>` obliga a quitar el float."""
    assert "display: flex" in _rule(".quiz-question-row")
    assert "display: block" in _rule(".quiz-question")


def test_the_take_template_wraps_the_question_in_that_inner_row():
    markup = TAKE.read_text("utf-8")

    row = markup.index('<span class="quiz-question-row">')
    assert row < markup.index('<span class="quiz-number"')
    assert row < markup.index('<span class="quiz-text">')
