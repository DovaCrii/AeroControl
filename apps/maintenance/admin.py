from django.contrib import admin
from .models import MaintenanceRecord,MaintenanceHistory
admin.site.register([MaintenanceRecord,MaintenanceHistory])
