---
tags: [aero-ops, arquitectura]
---

# 🏗 Arquitectura

## Estructura actual: Monolito Modular Django

```
D:\I+D\
├── AeroControl\             ← Código (git)
│   ├── apps/                ← 7 módulos Django
│   ├── config/              ← Settings split (base/dev/prod)
│   ├── templates/           ← Bootstrap 5
│   ├── static/              ← CSS
│   ├── scripts/             ← PowerShell automation
│   └── openspec/            ← SDD artifacts
│
└── AeroOpsDesk_Data\        ← Datos (NO git)
    ├── db/aero_ops.sqlite3
    ├── documents/
    ├── backups/
    ├── exports/
    └── logs/
```

## Módulos (apps/)

| App | Responsabilidad |
|-----|----------------|
| **core** | BaseModel (UUID, timestamps, is_active), backup engine, mixins |
| **registry** | Centros de costo, aeronaves, operadores, asignaciones |
| **compliance** | Documentos, alertas, reglas de vencimiento |
| **operations** | Permisos de vuelo SIGO, bitácora de vuelos |
| **maintenance** | Mantenimientos programados y no programados |
| **workboard** | Kanban personal con etapas y prioridades |
| **dashboard** | Vista ejecutiva de resumen |

## Decisiones clave

- **BaseModel abstracto** en `core/` — UUID como PK, `created_at`/`updated_at` automáticos, `is_active` para archive, `notes` opcional.
- **ContentType para documentos** — Los documentos se asocian a cualquier entidad (aeronave, operador, etc.) via GenericForeignKey, sin acoplar compliance al resto del dominio.
- **PROTECT en lugar de CASCADE** — Las referencias operativas usan `on_delete=PROTECT`. Nunca se pierde trazabilidad por borrado en cascada.
- **Settings split** — `base.py` (común), `dev.py` (DEBUG, SQLite), `prod.py` (producción). Variables vía `python-decouple`.

## Ruta de separación Backend/Frontend

```
Fase 1 (actual): Django templates + Bootstrap 5
    ↓
Fase 2: DRF serializers + viewsets (misma lógica, nueva capa)
    ↓
Fase 3: SPA Vue.js/React consumiendo API
    ↓
Fase 4: PostgreSQL, Redis, producción multi-usuario
```

## Document Management

Los documentos se almacenan en:
```
{DOCUMENTS_DIR}/{doc_type_code}/{model_name}/{object_id}/{uuid}_{filename}
```

El replace de versión: marca el documento anterior como `is_current_version=False` y crea uno nuevo con `is_current_version=True`. Ambos se conservan para trazabilidad.
