"""Sólo el `help_text` de `WorkAreaType.chapter`: no toca la base.

El texto original traía un ejemplo con tilde ("Capítulo J - DAN 137") y el gate
exige que **las cadenas fuente estén en inglés** — un literal acentuado en el
código queda fuera del alcance del catálogo (`test_source_strings_are_written_
in_english`). Se reescribió después de generar `0019`, que ya estaba en `main`.

Va como migración aparte y no reescribiendo `0019` porque esa ya se aplicó:
en un repo compartido las migraciones son append-only, igual que el historial.
Django la exige aunque no cambie ni una columna — `makemigrations --check` es
parte del gate, y su trabajo es que el estado declarado y el de los archivos no
se separen en silencio.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0019_r93_flight_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workareatype',
            name='chapter',
            field=models.CharField(blank=True, help_text='As SIGO shows it, with its DAN 137 chapter.', max_length=60, verbose_name='Regulatory chapter'),
        ),
    ]
