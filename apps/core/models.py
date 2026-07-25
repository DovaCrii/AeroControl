import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


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


class OperationalTenant(BaseModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TenantMembership",
        related_name="operational_tenants",
    )

    def __str__(self):
        return self.name


class TenantMembership(BaseModel):
    ROLES = [("member", "Member"), ("admin", "Admin")]
    tenant = models.ForeignKey(OperationalTenant, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES, default="member")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"], name="unique_tenant_membership"
            )
        ]


class AppendOnlyAuditQuerySet(models.QuerySet):
    """Prevent application code from mutating or deleting audit records."""

    def update(self, **kwargs):
        raise ValidationError("AuditEvent records are append-only.")

    def delete(self):
        raise ValidationError("AuditEvent records are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("AuditEvent records are append-only.")


class AuditEventManager(models.Manager.from_queryset(AppendOnlyAuditQuerySet)):
    pass


class AuditEvent(models.Model):
    """Append-only record of authenticated mutating and administrative actions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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

    objects = AuditEventManager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("AuditEvent records are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AuditEvent records are append-only.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["model_label", "object_id"]),
        ]


class JobRun(BaseModel):
    """Execution record for scheduled/management jobs.

    Written by the commands themselves (see apps.core.jobs.record_job_run) so
    the operator can tell whether the nightly work actually ran, and the
    administration centre can surface a stale-job warning later.
    """

    RESULT_RUNNING = "running"
    RESULT_OK = "ok"
    RESULT_ERROR = "error"
    RESULTS = [
        (RESULT_RUNNING, _("Running")),
        (RESULT_OK, _("Completed")),
        (RESULT_ERROR, _("Failed")),
    ]

    command = models.CharField(max_length=100)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    # "running" until the command finishes. The row used to be created with
    # result="ok" before the command executed, so a process killed mid-run
    # (scheduler kill, power loss, OOM) left a permanent success record - the
    # exact blind spot a stale-job warning would read. A row stuck in
    # "running" with an old started_at is now a detectable dead job.
    result = models.CharField(max_length=10, choices=RESULTS, default=RESULT_RUNNING)
    summary = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("job run")
        verbose_name_plural = _("job runs")
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["command", "-started_at"])]

    def __str__(self):
        return f"{self.command} · {self.started_at:%Y-%m-%d %H:%M} · {self.result}"

    @property
    def duration_seconds(self):
        if self.finished_at is None:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 2)


class ImportBatch(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
