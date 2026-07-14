$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py shell -c "from apps.compliance.models import DocumentType, AlertRule; DocumentType.objects.get_or_create(code='INS', defaults={'name':'Insurance'}); DocumentType.objects.get_or_create(code='MNT', defaults={'name':'Maintenance Certificate'}); DocumentType.objects.get_or_create(code='LIC', defaults={'name':'Operator License'}); AlertRule.objects.get_or_create(name='Qualification expiry', defaults={'entity_type':'Qualification','field_to_watch':'expiry_date','days_before_expiry':30})"
