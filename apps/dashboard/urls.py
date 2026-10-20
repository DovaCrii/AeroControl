from django.urls import path

from .compliance_section import compliance_section
from .views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    # LV-359: la sección «Cumplimiento» del panel (fragmento htmx o página completa).
    path("dashboard/compliance/", compliance_section, name="dashboard-compliance"),
]
