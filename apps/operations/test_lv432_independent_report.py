"""El reporte, el KML y el CSV de un log subido desde «Flight logs» (sin permiso).

`report._aircraft_facts` leía `permission.cost_center`; un análisis de LV-431 no tiene
permiso, así que el reporte imprimible y las dos descargas daban 500 en el caso que el
usuario usa todos los días. Quien puede ver los logs (`view_flightloganalysis`) tiene que
poder descargarlos.
"""

# ruff: noqa: F811 - fixtures compartidas
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightLogAnalysis

from .test_lv427_flight_log_analysis import centre, isolated_storage  # noqa: F401
from .test_lv429_dji_adapter import fake  # noqa: F401
from .test_lv431_flight_logs_section import ADD, VIEW, _upload, drone  # noqa: F401


def test_a_log_without_permit_downloads_report_kml_and_csv(fake, drone, centre):
    client = login_as(VIEW, ADD)
    _upload(client, centre, drone)
    analysis = FlightLogAnalysis.objects.get()
    assert analysis.permission is None and analysis.status == "ok"

    for name in (
        "flight-analysis-report",
        "flight-analysis-kml",
        "flight-analysis-csv",
    ):
        response = client.get(reverse(name, args=[analysis.pk]))
        assert response.status_code == 200, name

    report = client.get(reverse("flight-analysis-report", args=[analysis.pk]))
    assert drone.registration in report.content.decode()
