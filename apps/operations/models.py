from django.db import models
from apps.core.models import BaseModel
from apps.registry.models import Operator, Aircraft, CostCenter
class FlightPermission(BaseModel):
    STATUS_CHOICES=[("requested","Requested"),("approved","Approved"),("denied","Denied"),("completed","Completed")]
    permission_number=models.CharField(max_length=50,unique=True); operator=models.ForeignKey(Operator,on_delete=models.PROTECT); aircraft=models.ForeignKey(Aircraft,on_delete=models.PROTECT); cost_center=models.ForeignKey(CostCenter,on_delete=models.PROTECT); purpose=models.CharField(max_length=250); flight_date=models.DateField(); location=models.CharField(max_length=250); status=models.CharField(max_length=20,choices=STATUS_CHOICES,default="requested")
    def __str__(self): return self.permission_number
class FlightRecord(BaseModel):
    permission=models.ForeignKey(FlightPermission,on_delete=models.PROTECT,related_name="records"); actual_date=models.DateField(); departure_time=models.TimeField(); arrival_time=models.TimeField(); pilot=models.ForeignKey(Operator,on_delete=models.PROTECT); aircraft=models.ForeignKey(Aircraft,on_delete=models.PROTECT,related_name="flight_records")
