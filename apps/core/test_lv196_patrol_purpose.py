"""LV-196: "Patrullaje" entra al vocabulario de propósito.

Pedido del usuario mirando el selector del formulario del permiso: *"sumar
Patrullaje ya que se usará mucho"*.

No corrige nada de `R3.1`, que declaró este vocabulario cerrado y lo confirmó
contra los datos reales: los dos procedimientos SIGO del DAN 137 Cap. J son
Fotogrametría y Videos. Es una decisión de negocio del usuario, y su razón es
medible — hoy un patrullaje se registra como "Otro" con el texto en
`purpose_detail`, así que **no se puede contar ni filtrar**, que es exactamente
lo que un vocabulario cerrado existe para permitir. Un tercer procedimiento no
rompe la premisa; que el uso más frecuente quedara fuera del catálogo sí la
vaciaba.

Lo que estos tests fijan es lo que se decidió **y lo que se decidió no hacer**:
las filas históricas no se reclasifican. `PURPOSE_LEGACY_MAP` sólo acepta
coincidencias exactas y su regla es no adivinar, porque cada valor histórico real
que `R3.1a` encontró mezclaba más de un concepto.
"""

import pytest
from django.utils import translation

from apps.core.choices import PURPOSE_CHOICES, PURPOSE_LEGACY_MAP


def test_patrol_is_offered():
    assert "patrol" in dict(PURPOSE_CHOICES)


def test_other_stays_last():
    """ "Otro" es el escape, no una opción más: en el desplegable tiene que quedar
    al final, o se lee como una alternativa al mismo nivel que las tres reales."""
    assert PURPOSE_CHOICES[-1][0] == "other"


def test_the_two_sigo_procedures_are_untouched():
    """El contrapeso: sumar uno no puede alterar los dos que nombran los
    procedimientos del DAN 137 Cap. J."""
    values = [value for value, _label in PURPOSE_CHOICES]

    assert values[:2] == ["photogrammetry", "video"]


def test_it_reads_as_patrullaje_in_spanish():
    """Sin el prefijo "Procedimiento de" que llevan los otros dos: ésos se llaman
    así en el papel de SIGO, y el patrullaje no es uno de esos procedimientos."""
    with translation.override("es"):
        assert str(dict(PURPOSE_CHOICES)["patrol"]) == "Patrullaje"


def test_the_legacy_map_recognises_the_exact_word_only():
    """La regla del mapa es coincidencia exacta y nunca adivinar."""
    assert PURPOSE_LEGACY_MAP["patrullaje"] == "patrol"
    assert "patrullaje aéreo" not in PURPOSE_LEGACY_MAP


@pytest.mark.django_db
def test_a_permit_can_be_saved_with_it():
    """De punta a punta contra la base: el valor nuevo pasa la validación de
    `choices`, que es lo que un `AlterField` sin migración de datos deja
    listo."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.operations.models import FlightPermission
    from apps.registry.models import CostCenter

    today = timezone.localdate()
    permit = FlightPermission.objects.create(
        internal_folio="JEJ-2026-196",
        cost_center=CostCenter.objects.create(code="CC738", name="MLP"),
        purpose="patrol",
        valid_from=today,
        valid_until=today + timedelta(days=30),
        location="Quebrada km 13",
        area_type="unpopulated",
    )
    permit.full_clean()

    assert permit.get_purpose_display()
