"""`T1.3`: el historial de estados se escribe **con** el guardado, no antes de él.

Lo hacía `signals.track_status_changes`, una señal `pre_save`. Dos defectos, uno de
ellos medido el 2026-10-05 con una prueba:

- **Corre antes del bloque atómico de `Model.save`** (y la aplicación no usa
  `ATOMIC_REQUESTS`). Si el guardado falla después —una unicidad, una restricción—,
  la fila del historial ya está escrita: `PermissionHistory` quedó con
  `approved → denied` mientras la base conservaba `approved`. Un registro de
  trazabilidad que afirma un cambio que nunca ocurrió.
- Escribe **otra fila** desde dentro de una señal de un guardado que todavía no
  aterrizó: la misma clase de problema que `R6.1` ya enseñó con `Alert.resolve()`.

Este mixin hace lo mismo y en el orden correcto: abre una transacción, lee el valor
que hay en la base, guarda la fila y **después** escribe el historial, todo junto. Si
el guardado falla, el historial se deshace con él.

⚠️ **Lo que a propósito NO cambia**, porque la premisa de este paso es que todo siga
funcionando igual:

- El valor anterior se sigue leyendo **de la base**, dentro de la transacción, y no
  del valor cargado en memoria. Una vista que leyó el registro hace un rato y lo
  guarda ahora compara contra lo que hay hoy, como siempre. Guardar esa consulta
  (con `from_db`) sería una optimización, y las optimizaciones se hacen después de
  que la corrección esté probada.
- La atribución sigue viajando en `_changed_by`, `_changed_by_user` y
  `_transition_notes`. Reemplazarlos por una API explícita (`transition_to`) es una
  decisión aparte: el administrador y «Corregir el estado» asignan `status` directo,
  y exigirla los rompería.
- `queryset.update()` y los escritos en bloque no pasan por `save()` y siguen sin
  escribir historial, como con la señal (`expire_permissions` lo escribe a mano).

**Un cambio deliberado**: con `update_fields` que no incluya el campo vigilado, no se
escribe historial. La base no cambió de estado en ese guardado, y la señal vieja
escribía igual un `approved → denied` que nunca ocurrió.
"""

from django.apps import apps
from django.db import transaction


class StatusHistoryMixin:
    """Escribe una fila de historial cuando el campo vigilado cambia al guardar.

    Cada modelo declara `STATUS_HISTORY = ("app.ModeloHistorial", "<fk al
    registro>", "<campo vigilado>")`. El campo vigilado no siempre es `status`: el
    seguro de una aeronave avanza por `insurance_status`.

    Va **antes** de `models.Model` en las bases, y su `save` queda debajo del que
    el modelo ya tenga: corre dentro de él, después de sus propias reconciliaciones
    y dentro de la transacción que ese `save` abra.
    """

    STATUS_HISTORY = None

    def save(self, *args, **kwargs):
        config = self.STATUS_HISTORY
        if config is None:
            return super().save(*args, **kwargs)
        history_label, relation, field = config
        update_fields = kwargs.get("update_fields")
        # Una fila nueva no tiene estado anterior, y un `update_fields` sin el campo
        # no lo guarda: en los dos casos no hay cambio que registrar.
        if self._state.adding or (
            update_fields is not None and field not in update_fields
        ):
            return super().save(*args, **kwargs)
        with transaction.atomic():
            previous = (
                type(self)
                ._base_manager.filter(pk=self.pk)
                .values_list(field, flat=True)
                .first()
            )
            result = super().save(*args, **kwargs)
            current = getattr(self, field)
            if previous is not None and previous != current:
                self._write_status_history(
                    history_label, relation, field, previous, current
                )
            return result

    def _write_status_history(self, history_label, relation, field, previous, new):
        history_model = apps.get_model(history_label)
        values = {
            relation: self,
            "previous_status": previous,
            "new_status": new,
            "changed_by": getattr(self, "_changed_by", "system"),
            "changed_by_user": getattr(self, "_changed_by_user", None),
        }
        if any(f.name == "notes" for f in history_model._meta.fields):
            values["notes"] = getattr(self, "_transition_notes", "")
        history_model.objects.create(**values)
