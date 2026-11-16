from django.contrib import admin
from .models import (
    AircraftLogbook,
    MaintenanceHistory,
    MaintenanceProgram,
    MaintenanceRecord,
    WorkshopIntake,
)

admin.site.register(
    [
        MaintenanceRecord,
        MaintenanceHistory,
        WorkshopIntake,
        MaintenanceProgram,
        AircraftLogbook,
    ]
)
