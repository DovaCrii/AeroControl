"""LV-230: el tipo de documento que `LV-225` duplicó, fusionado.

Lo encontró el usuario mirando el expediente: *"diferencia entre carta del
mandante en ficha y carta de permiso adjunta, al final cumplen la misma función;
lo importante es ver para no repetir la información, eso es la clave, ya que en
permisos similares debo subir varias veces la misma carta"*.

Confirmado con él: **`dgac-flight-permit` es la carta del mandante**, así que el
`client-authorization-letter` que se creó el día anterior describía el mismo
papel.

⚠️ **La causa no fue una lectura descuidada, y por eso vale un archivo de tests.**
El tipo preexistente se llamaba *"Autorización DGAC (carta de permiso)"* mientras
su propia documentación (`LV-64`) decía que es *"lo que va **hacia** la DGAC"* — el
nombre apuntaba en la dirección contraria, y encima llevaba `requires_expiry=True`,
que no encaja con una solicitud. **Un nombre equivocado hizo inventar un tipo
nuevo.** Lo que estos tests protegen es que el nombre siga diciendo la verdad.

El daño fue real y medible: el expediente pedía los dos papeles, el usuario subió
el mismo PDF dos veces, y la bandeja mostró **dos alertas por un solo
vencimiento**.
"""

from importlib import import_module

import pytest
from django.core.management import call_command

from apps.compliance.models import DocumentType
from apps.operations.dossier import PERMIT_LETTER

RETIRED = "client-authorization-letter"


class TestThereIsOnlyOneClientLetterType:
    @pytest.mark.django_db
    def test_the_duplicated_type_is_not_seeded_any_more(self):
        call_command("seed_document_types")

        assert not DocumentType.objects.filter(code=RETIRED).exists()

    @pytest.mark.django_db
    def test_the_surviving_type_says_what_it_is(self):
        """**El arreglo de fondo.** Un nombre que miente cuesta un tipo duplicado.

        Decía "Autorización DGAC (carta de permiso)", que sugiere un papel emitido
        por la DGAC. Lo emite el cliente.
        """
        call_command("seed_document_types")

        name = DocumentType.objects.get(code=PERMIT_LETTER).name
        assert "mandante" in name.lower()
        assert "autorización dgac" not in name.lower()

    @pytest.mark.django_db
    def test_it_does_not_demand_an_expiry_date(self):
        """No toda carta del mandante trae plazo escrito.

        Llevaba `requires_expiry=True` de cuando se la creía una autorización de
        la DGAC, que sí vence. Exigir la fecha obligaría a **inventarla** para
        poder cargar el papel — el mal que `LV-219` quitó del alta del permiso.
        """
        call_command("seed_document_types")

        assert not DocumentType.objects.get(code=PERMIT_LETTER).requires_expiry


class TestTheDossierAsksForTwoPapersNotThree:
    @pytest.mark.django_db
    def test_the_client_letter_appears_once(self):
        """Lo que el usuario vio en pantalla: dos filas para un mismo papel."""
        from apps.operations.dossier import operational_dossier
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        permit = FlightPermission.objects.create(
            cost_center=CostCenter.objects.create(code="CC1", name="Uno"),
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
        )

        keys = [item.key for item in operational_dossier(permit)["items"]]

        assert keys.count("permit_letter") == 1
        assert "client_letter" not in keys


class TestTheMigrationMovesDocumentsWithoutLosingThem:
    @pytest.mark.django_db
    def test_the_migration_carries_the_documents_over(self):
        """El traslado, ejercitado sobre la función real de la migración.

        Se importa y se corre con los modelos vivos: un test que sólo leyera el
        archivo comprobaría que el texto existe, no que mueve documentos.
        """
        from datetime import date

        from django.apps import apps as django_apps
        from django.contrib.contenttypes.models import ContentType

        # `importlib` porque el modulo empieza con digito: `from ... import
        # 0025_...` no es sintaxis valida.
        migration = import_module(
            "apps.compliance.migrations.0025_lv230_the_client_letter_was_duplicated"
        )
        from apps.compliance.models import Document
        from apps.registry.models import Aircraft, CostCenter

        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        aircraft = Aircraft.objects.create(
            registration="CC-AAA",
            type="Fixed",
            model="A",
            manufacturer="Maker",
            cost_center=cost_center,
        )
        keep = DocumentType.objects.create(
            code=PERMIT_LETTER,
            name="Autorización DGAC (carta de permiso)",
            requires_expiry=True,
        )
        drop = DocumentType.objects.create(code=RETIRED, name="Carta del mandante")
        carried = Document.objects.create(
            title="La carta",
            doc_type=drop,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            file_path="carta/x.pdf",
            issue_date=date(2026, 8, 14),
        )

        migration.merge(django_apps, None)

        carried.refresh_from_db()
        keep.refresh_from_db()
        # El documento sobrevive, con su archivo y su fecha, apuntando al tipo
        # que se queda.
        assert carried.doc_type_id == keep.pk
        assert carried.file_path == "carta/x.pdf"
        # Y el tipo duplicado se fue, ya sin nada colgando.
        assert not DocumentType.objects.filter(code=RETIRED).exists()
        assert "mandante" in keep.name.lower()
        assert keep.requires_expiry is False

    @pytest.mark.django_db
    def test_it_survives_an_installation_that_never_had_the_duplicate(self):
        """Una instalación que nunca sembró el tipo duplicado no debe romperse."""
        from django.apps import apps as django_apps

        # `importlib` porque el modulo empieza con digito: `from ... import
        # 0025_...` no es sintaxis valida.
        migration = import_module(
            "apps.compliance.migrations.0025_lv230_the_client_letter_was_duplicated"
        )

        DocumentType.objects.create(
            code=PERMIT_LETTER, name="Autorización DGAC (carta de permiso)"
        )

        migration.merge(django_apps, None)  # no levanta

        assert "mandante" in DocumentType.objects.get(code=PERMIT_LETTER).name.lower()
