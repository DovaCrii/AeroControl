---
tags: [aero-ops, index, documentacion]
---

# 🛩 AeroOps Desk

**Consola local para control y seguimiento de operaciones RPA.**

Repositorio: `D:\I+D\aero-ops-desk`  
Datos: `D:\I+D\AeroOpsDesk_Data\`

---

## 📋 Documentación

| Nota | Descripción |
|------|-------------|
| [[Proyecto]] | Visión general, origen, objetivos y alcance |
| [[Arquitectura]] | Decisiones técnicas, estructura, separación code/data |
| [[Roadmap]] | Fases de desarrollo y próximos pasos |
| [[Seguimiento]] | Registro de sesiones y avances |

## 🚀 Inicio rápido

```powershell
cd D:\I+D\aero-ops-desk
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe manage.py createsuperuser
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

## 🔗 Links

- GitHub: https://github.com/DovaCrii/aero-ops-desk
- [[openspec/README]] — SDD artifacts
