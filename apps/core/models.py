import uuid
from django.db import models
from django.conf import settings


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


class AuditEvent(models.Model):
    """Append-only record of authenticated mutating and administrative actions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=32)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    status_code = models.PositiveSmallIntegerField()
    model_label = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["model_label", "object_id"]),
        ]


class ImportBatch(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="import_batches",
    )
    entity = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="applied")
    rows = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    created_ids = models.JSONField(default=list, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
