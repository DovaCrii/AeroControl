from django.contrib import admin
from .models import CostCenter, Aircraft, Operator, Assignment, Qualification

admin.site.register([CostCenter, Aircraft, Operator, Assignment, Qualification])
