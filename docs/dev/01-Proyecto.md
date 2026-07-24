---
tags: [aero-ops, proyecto]
---

# 🎯 Proyecto

## Origen

AeroControl nace de la realidad operativa de la gestión de flotas RPA (Remotely Piloted Aircraft): planillas Excel dispersas, credenciales vencidas rastreadas en hilos de correo, registros de mantenimiento散ados en carpetas, y permisos de vuelo armados sobre la hora.

## Propósito

Ser una **consola local de operaciones** — no una plataforma SaaS, no un dashboard en la nube. Vive en la máquina del operador, habla con una base SQLite local, y mantiene los datos operativos completamente bajo control del usuario.

## Principios

1. **Code/Data isolation** — El código y los datos nunca se mezclan. El repo es sólo código.
2. **Archival, no delete** — Nunca se elimina un registro operativo. Se archiva con `is_active=False`.
3. **Local-first** — Sin dependencia de servicios cloud. La app funciona 100% offline.
4. **Fat models, thin views** — La lógica de negocio vive en los modelos, preparada para una futura API REST.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Django 6.0, Python 3.12 |
| Base de datos | SQLite (local, aislada del repo) |
| Frontend | Bootstrap 5 (fase actual) |
| API futura | Django REST Framework |
| Frontend futuro | Vue.js o React (SPA) |
