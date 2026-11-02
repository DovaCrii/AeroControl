from django.contrib import admin
from .models import MaintenanceRecord, MaintenanceHistory, WorkshopIntake

admin.site.register([MaintenanceRecord, MaintenanceHistory, WorkshopIntake])
