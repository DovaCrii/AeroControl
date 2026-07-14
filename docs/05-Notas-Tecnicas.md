---
tags: [aero-ops, notas-tecnicas]
---

# ⚙ Notas Técnicas

## Patrones

### BaseModel (core/models.py)
```python
class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        abstract = True
```
Todos los modelos del dominio heredan de `BaseModel`. El archival con `is_active=False` reemplaza al borrado físico.

### SearchMixin (core/views.py)
```python
class SearchMixin:
    search_fields = []

    def get_queryset(self):
        # ... Q object OR search + is_active filter
```
Aplica a todas las listas. Cada ListView define `search_fields` con los campos a buscar.

### Document Upload
Los archivos se guardan manualmente (no Django FileField) para mantener el storage fuera del repo:
1. Form recibe el archivo
2. `document_upload_path()` genera ruta relativa
3. Se guarda en `{DOCUMENTS_ROOT}/{rel_path}`
4. La ruta relativa se almacena en `Document.file_path`

## Gotchas

- **Document.file_path es CharField**, no FileField — porque queremos storage fuera del repo.
- **PROTECT en lugar de CASCADE** en todas las FK operacionales — porque archive no es delete.
- **El context processor `unresolved_alert_count`** está registrado en settings/base.py TEMPLATES.
- **DOCUMENTS_ROOT** se define en settings/base.py desde la env var DOCUMENTS_DIR. Misma variable que MEDIA_ROOT para simplificar.
- **Las templates de compliance** están en `templates/compliance/` (project-level), no en `apps/compliance/templates/compliance/`.

## CLI

```powershell
# Generar alertas manualmente
python manage.py generate_alerts

# Backup
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1

# Verificar
python manage.py check
```
