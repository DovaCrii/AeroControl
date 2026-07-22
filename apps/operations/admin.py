from django.contrib import admin
from .models import FlightPermission, FlightRecord

admin.site.register([FlightPermission, FlightRecord])
