from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
import re
from pathlib import Path
from uuid import uuid4

from apps.core.models import BaseModel


def document_upload_path(instance, filename):
    """Return the relative storage path used for manually saved documents."""
    def safe_segment(value, fallback):
        segment = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(value)).name).strip("._")
        return segment or fallback

    model_name = instance.content_type.model if instance.content_type_id else "entity"
    doc_type_code = safe_segment(instance.doc_type.code, "document")
    safe_model = safe_segment(model_name, "entity")
    safe_filename = safe_segment(filename, "upload")
    return f"{doc_type_code}/{safe_model}/{instance.object_id}/{uuid4()}_{safe_filename}"


class DocumentType(BaseModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    requires_expiry = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Document(BaseModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_current_version = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class AlertRule(BaseModel):
    name = models.CharField(max_length=150)
    entity_type = models.CharField(max_length=100)
    field_to_watch = models.CharField(max_length=100)
    days_before_expiry = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)


class Alert(BaseModel):
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
