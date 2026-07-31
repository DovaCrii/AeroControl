# ADR-0001: Modelo de tenancy (T3.2 / F-08)

**Estado:** Aceptado (Opción A, por fases — usuario 2026-07-31)
**Fecha:** 2026-07-31
**Decisor:** usuario (dueño del producto)

> **Progreso:**
> - **Fase 0a** ✅ — helper `apps/core/tenancy.py::get_default_tenant` (default del
>   FK, evita churn de tests) + `CostCenter`/`Aircraft`/`Operator.tenant` a
>   `NOT NULL` con backfill (migr. `registry` 0018/0019).
> - **Fase 0b** ✅ — FK `tenant` propio en `Document` (GFK, no deriva; cierra F-05)
>   y `AlertRule` (config, sin padre) (migr. `compliance` 0010). Decidido con el
>   usuario: **catálogos globales** (DocumentType/QualificationType sin tenant);
>   los demás agregados (Qualification, MaintenanceRecord, GeoPlan,
>   FlightPermission, asignaciones, historias) **derivan** el tenant de su padre
>   único vía el mixin de la Fase 2 — no llevan FK propio.
> - **Fase 0 completa**: todo registro scopeable puede resolver un tenant.
>
> - **Fase 1** ✅ — `apps/core/tenancy.py::visible_tenant_ids(user)` como fuente
>   única de "qué tenants ve el usuario" (None=superuser; sus memberships; o el
>   default si no tiene ninguna). Reemplaza las 3 copias inline (calendario
>   permisos+asignaciones, lista de Assignment). El fallback al default corrige
>   un bug latente: un no-superuser sin membership veía calendario/listas vacíos.
>   Con test de aislamiento (usuario de otro tenant no ve los datos del default).
>
> Siguen: **Fase 2** (cambiar el OR-sobre-3-FKs por ruta canónica única —
> la parte sensible, se hace junto con la matriz de aislamiento de Fase 4),
> Fase 3 (constraints únicas por tenant).
**Relacionados:** MASTER_PLAN T3.2 / T3.3 / T4.1 / T4.2 · AUDIT_CLAUDE F-03..F-06, F-08, F-10

## Contexto

AeroControl corre hoy en producción (VM `p340`) como **un solo tenant de
facto**: hay 0 filas en `OperationalTenant`, y el campo `tenant` que existe está
en `NULL` en todos los registros. La infraestructura de tenancy está **a medio
construir**, y así es un riesgo latente, no una funcionalidad:

- Solo **4 de ~21 modelos** tienen `tenant` (`CostCenter`, `Aircraft`,
  `Operator`, `KanbanBoard`); los 17 restantes no (`Document`, `FlightPermission`,
  `Alert`, `Qualification`, `MaintenanceRecord`, historias, asignaciones, geo…).
- Los 4 son **nullable y se añadieron sin backfill** → todo registro existente
  tiene `tenant = NULL`. Ningún formulario de registry/compliance/operations
  expone `tenant` (solo Kanban y el admin) → **todos los datos operativos son
  globales**.
- El scoping de lectura es un **OR sobre tres FKs** (`apps/core/views.py`,
  `apps/registry/views.py`): un permiso con aeronave del tenant A y operador del
  tenant B se filtra a **ambos**. Es fuga por diseño — hoy inofensiva porque
  `tenant=NULL` es universal, real el día que exista un segundo tenant.
- Hay **tres implementaciones distintas** del scoping y **ninguna validación**
  que impida mezclar tenants dentro de un `FlightPermission` (M2M sin `clean()`).
- Faltan `UniqueConstraint(tenant, code)` / `(tenant, employee_id)` /
  `(tenant, permission_number)`: hoy la unicidad es **global**, lo que bloquea
  que dos tenants reusen un código (F-10).

**Fuerzas en juego.** (1) El valor de multi-tenant se materializa solo cuando se
**centraliza el servidor para varias organizaciones** o se retoma **DJI Cloud
API** (T6.7), y **ninguna es inminente**. (2) Pero el costo de hacerlo **crece
con los datos acumulados**: hoy la base es diminuta (11 CC, 41 operadores, 14
aeronaves, 0 documentos/alertas), así que un backfill + `NOT NULL` + constraints
es barato y de bajo riesgo; en un año, con documentos, alertas e historiales, es
una migración pesada y peligrosa. (3) Tres implementaciones divergentes de
scoping son deuda que cuesta mantener aunque nunca haya multi-tenant.

## Decisión

**Establecer ahora la _fundación_ de tenancy — correcta, con backfill a un
tenant por defecto y `NOT NULL` — sin construir todavía la gestión multi-tenant
de cara al usuario.** Es la opción "barato ahora": deja el esquema y el scoping
sólidos y unificados, cierra F-03..F-06/F-08/F-10 (prerequisitos de la
centralización), y no invierte en UI de organizaciones hasta que exista una
segunda real.

Concretamente: `tenant` (FK PROTECT, `NOT NULL`) en los 17 modelos que faltan;
migración de datos que crea un **tenant por defecto** y backfilea todo a él;
**un** `TenantScopedQuerysetMixin` que reemplaza las tres implementaciones OR;
`clean()` que rechaza mezclar tenants en un `FlightPermission`; y
`UniqueConstraint` compuestas con `tenant`. El `tenant` se **deriva del contexto
del usuario** (su `TenantMembership`), no se expone en cada formulario.

## Opciones consideradas

### Opción A — Fundación completa ahora (recomendada)
Migrar los 17 modelos + backfill a tenant por defecto + `NOT NULL` + mixin único
+ constraints + validación, sin UI multi-tenant.

| Dimensión | Evaluación |
|---|---|
| Complejidad | Alta (migración de datos en ~17 tablas) pero **acotada** por lo pequeño de la base |
| Costo | Bajo **hoy**; crece rápido si se difiere |
| Escalabilidad | Desbloquea centralización y DJI sin re-migrar |
| Riesgo | Medio — mitigado por base pequeña, backfill idempotente, backup previo, y tests de aislamiento (T4.2) |

**Pros:** cierra el hazard irreversible mientras es barato; unifica 3 scopings en 1; reversibilidad segura hoy. **Contras:** trabajo XL sobre una app que funciona; el beneficio es diferido.

### Opción B — No hacer nada (mantener single-tenant)
| Dimensión | Evaluación |
|---|---|
| Complejidad | Nula ahora |
| Costo | Explota después (migrar con datos acumulados) |
| Riesgo | El scoping OR y la falta de validación quedan como deuda; F-08/F-10 abiertos |

**Pros:** cero esfuerzo, la app anda. **Contras:** patea un problema que se encarece con el tiempo; bloquea centralización/DJI.

### Opción C — Solo unificar el scoping (sin `tenant` en 17 modelos)
Reemplazar las 3 implementaciones OR por un mixin único, pero sin agregar
`tenant` a los modelos que faltan.

| Dimensión | Evaluación |
|---|---|
| Complejidad | Baja |
| Costo | Bajo |
| Riesgo | Deja F-08 (17 modelos sin tenant) abierto; no habilita multi-tenant real |

**Pros:** mata la deuda de los 3 scopings barato. **Contras:** media solución; el `NOT NULL`+backfill sigue pendiente y se encarece igual.

## Análisis de trade-offs

El eje es **"barato ahora vs. caro después"** contra **"beneficio diferido"**.
La base diminuta de hoy inclina fuerte hacia A: la parte cara de A (backfill +
`NOT NULL` + constraints sobre datos que podrían violarlas) es trivial con 66
filas de dominio y 0 documentos, y se vuelve un proyecto en sí misma cuando haya
miles. B ahorra esfuerzo hoy a cambio de un costo mayor garantizado si el
roadmap (centralización/DJI) se concreta. C es un punto intermedio honesto si se
quiere reducir riesgo de scope: mata la peor deuda de mantenimiento (3 scopings)
sin comprometerse al `NOT NULL`.

**Recomendación:** **A**, ejecutada **por fases con revisión entre cada una**
(abajo), para que un cambio XL no entre en un solo PR gigante — justo el
antipatrón que `AGENTS.md` prohíbe.

## Consecuencias

- **Más fácil:** centralizar para una segunda organización sin re-migrar; DJI;
  constraints de unicidad por tenant; un solo lugar de scoping que auditar.
- **Más difícil:** cada modelo nuevo debe declarar `tenant` (se documenta en
  `AGENTS.md` como parte del DoD de "modelo"); los tests deben usar la fixture
  `two_tenant_world` (T4.1).
- **A revisar:** cómo se resuelve el `tenant` del request (middleware que lo fija
  desde `TenantMembership`); qué pasa con un usuario sin membership (¿tenant por
  defecto? ¿403?). Se decide en la Fase 1.

## Plan de acción (por fases, un PR cada una)

1. [ ] **Fase 0 — Fundación de datos.** Migración: crear tenant por defecto,
   añadir `tenant` nullable a los 17 modelos, backfill al tenant por defecto,
   luego `NOT NULL` (migraciones separadas: add-null → backfill → alter-not-null,
   para que sea reversible y segura). Backup previo del `.sqlite3`.
2. [ ] **Fase 1 — Resolución de tenant del request.** Middleware/util que fija el
   tenant activo desde `TenantMembership`; decisión sobre usuarios sin membership.
3. [ ] **Fase 2 — `TenantScopedQuerysetMixin` único.** Reemplaza las 3
   implementaciones OR (core/registry) por scoping por `tenant` exacto; borra la
   fuga del OR. `FlightPermission.clean()` rechaza roster mixto de tenants.
4. [ ] **Fase 3 — Constraints (T3.3/F-10).** `UniqueConstraint(tenant, code)` en
   CostCenter, `(tenant, employee_id)` en Operator, `(tenant, permission_number)`
   en FlightPermission, etc.; `CheckConstraint` donde aplique.
5. [ ] **Fase 4 — Tests de aislamiento (T4.1/T4.2).** Fixture `two_tenant_world`,
   matriz cross-tenant por vista; corregir `workboard/tests.py:511-525` que hoy
   codifica el modo permisivo como esperado.
6. [ ] **Fase 5 — DoD.** Actualizar `AGENTS.md`: todo modelo nuevo lleva `tenant`;
   toda vista de dominio scopea por tenant.

> Nada de esto agrega UI de gestión de organizaciones: el `tenant` se deriva del
> usuario. Esa UI se construye cuando exista una segunda organización real.
