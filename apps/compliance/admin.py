from django.contrib import admin
from .models import DocumentType, Document, AlertRule, Alert
admin.site.register([DocumentType, Document, AlertRule, Alert])
