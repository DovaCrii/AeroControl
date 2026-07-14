from django.db import models
from apps.core.models import BaseModel
from apps.registry.models import Aircraft
class MaintenanceRecord(BaseModel):
    TYPES=[("scheduled","Scheduled"),("unscheduled","Unscheduled"),("emergency","Emergency")]; STATUSES=[("pending","Pending"),("in_progress","In progress"),("completed","Completed")]
    aircraft=models.ForeignKey(Aircraft,on_delete=models.PROTECT,related_name="maintenance_records"); maintenance_type=models.CharField(max_length=20,choices=TYPES); description=models.TextField(); scheduled_date=models.DateField(); completed_date=models.DateField(null=True,blank=True); performed_by=models.CharField(max_length=150); cost=models.DecimalField(max_digits=12,decimal_places=2,default=0); status=models.CharField(max_length=20,choices=STATUSES,default="pending")
class MaintenanceHistory(BaseModel):
    record=models.ForeignKey(MaintenanceRecord,on_delete=models.CASCADE,related_name="history"); changed_at=models.DateTimeField(auto_now_add=True); previous_status=models.CharField(max_length=20); new_status=models.CharField(max_length=20); changed_by=models.CharField(max_length=150)
