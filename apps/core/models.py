import uuid
from django.db import models


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        abstract = True


class BackupConfig(BaseModel):
    backup_enabled = models.BooleanField(default=True)
    backup_path = models.CharField(max_length=500)
    auto_backup_interval_hours = models.PositiveIntegerField(default=24)
    last_backup = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.backup_path
