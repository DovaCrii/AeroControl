"""LV-142: una `UniqueConstraint` que menciona `tenant` no se validaba nunca.

El agujero no era de tres formularios: era de clase. Django omite una constraint
completa cuando alguno de sus campos está excluido de la validación
(`UniqueConstraint.validate()` retorna temprano), y `_get_validation_exclusions()`
excluye todo campo ausente del formulario. `tenant` no está en **ningún**
formulario de escritura del proyecto — viene del `default` del campo—, así que
cualquier constraint que lo mencione pasaba de largo y el duplicado moría como
`IntegrityError`, o sea 500 sin mensaje.

`AeroModelForm.validate_constraints` devuelve `tenant` al alcance sólo para esa
comprobación. Los `clean_*` de cada formulario siguen siendo los que dicen quién
tiene el valor; esto es la red para el que se escriba mañana y olvide el suyo.
"""

import pytest
from django.apps import apps
from django.db.models import UniqueConstraint

from apps.core.forms import AeroModelForm
from apps.core.models import OperationalTenant
from apps.registry.models import Operator

# Las constraints por tenant que existen hoy. La lista está congelada a
# propósito: si mañana aparece una nueva, este test falla y obliga a decidir si
# lleva su propio mensaje amable (un `clean_*`, como `Operator.employee_id`) o se
# queda con el genérico de la red. Sin la lista, una constraint nueva heredaría
# la red en silencio y nadie revisaría su mensaje.
TENANT_SCOPED_CONSTRAINTS = {
    ("core.TenantMembership", "unique_tenant_membership"),
    ("registry.CostCenter", "registry_costcenter_tenant_code_uniq"),
    ("registry.Operator", "registry_operator_tenant_employee_uniq"),
    ("compliance.ComplianceSnapshot", "compliance_snapshot_cc_date_uniq"),
    ("compliance.ComplianceSnapshot", "compliance_snapshot_total_date_uniq"),
}


class _BareOperatorForm(AeroModelForm):
    """Un formulario sin `clean_employee_id`, para ver actuar a la red.

    `OperatorForm` atrapa el duplicado antes con su propio mensaje, así que sobre
    él la red nunca se nota. Este formulario es el equivalente al que alguien
    escribirá mañana sobre un modelo con constraint por tenant sin acordarse de
    agregar el chequeo amable.
    """

    class Meta:
        model = Operator
        fields = ["employee_id", "full_name"]


def _tenant_scoped_constraints():
    found = set()
    for model in apps.get_models():
        for constraint in model._meta.constraints:
            fields = getattr(constraint, "fields", None) or ()
            if isinstance(constraint, UniqueConstraint) and any(
                "tenant" in field for field in fields
            ):
                found.add((model._meta.label, constraint.name))
    return found


def test_the_frozen_list_of_tenant_scoped_constraints_is_still_accurate():
    assert _tenant_scoped_constraints() == TENANT_SCOPED_CONSTRAINTS


@pytest.mark.django_db
class TestTheSafetyNet:
    def test_a_tenant_scoped_unique_constraint_reaches_the_form(self):
        Operator.objects.create(employee_id="E-500", full_name="Ana Rivas")

        form = _BareOperatorForm(data={"employee_id": "E-500", "full_name": "Luis Paz"})

        assert not form.is_valid()

    def test_the_same_value_in_another_tenant_is_allowed(self):
        # La red no puede pasarse de estricta: la constraint es por tenant, así
        # que dos organizaciones pueden reusar el mismo número de empleado.
        other = OperationalTenant.objects.create(name="Otra empresa")
        Operator.objects.create(
            tenant=other, employee_id="E-500", full_name="Ana Rivas"
        )

        form = _BareOperatorForm(data={"employee_id": "E-500", "full_name": "Luis Paz"})

        assert form.is_valid(), form.errors

    def test_editing_a_row_does_not_collide_with_itself(self):
        operator = Operator.objects.create(employee_id="E-500", full_name="Ana Rivas")

        form = _BareOperatorForm(
            data={"employee_id": "E-500", "full_name": "Ana Rivas Soto"},
            instance=operator,
        )

        assert form.is_valid(), form.errors
