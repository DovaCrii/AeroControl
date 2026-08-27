"""LV-168: partir el enunciado de la prueba en renglones, sólo para mostrarlo.

Va como filtro y no como una clave más de `draw_questions` porque la pantalla de
revisión (`assessment_detail.html`) no lee el banco: lee la copia archivada en el
intento. Un filtro sirve a las dos, y con eso los intentos ya rendidos también se
leen bien.
"""

from django import template

from apps.registry import assessments

register = template.Library()


@register.filter
def enumerated_lines(text):
    return assessments.enumerated_lines(text)
